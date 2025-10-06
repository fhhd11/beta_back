"""
AI Agent Platform API Gateway
Production-ready FastAPI gateway for unified access to microservice ecosystem.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.config.settings import get_settings
from src.config.logging import setup_logging
from src.middleware.auth import AuthMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.circuit_breaker import CircuitBreakerMiddleware
from src.routers import system, user, letta, agents, templates, llm_proxy, ams
from src.utils.metrics import setup_metrics, request_duration, request_counter
from src.utils.cache import get_redis_client
from src.utils.exceptions import setup_exception_handlers

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger(__name__)

logger.info("Application starting", version=settings.version, environment=settings.environment)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting AI Agent Platform API Gateway", version=settings.version)
    
    # Initialize Redis connection (optional)
    if settings.enable_caching or settings.enable_rate_limiting:
        try:
            redis_client = await get_redis_client()
            app.state.redis = redis_client
            logger.info("Redis connection established")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            logger.warning("Continuing without Redis - caching and rate limiting will be disabled")
            settings.enable_caching = False
            settings.enable_rate_limiting = False
    else:
        logger.info("Redis disabled - caching and rate limiting are off")
    
    # Setup metrics
    setup_metrics()
    logger.info("Prometheus metrics initialized")
    
    # Validate upstream services connectivity
    if settings.environment == "production":
        await _validate_upstream_services()
    
    logger.info("API Gateway startup completed")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Gateway")
    
    # Close Redis connection
    if hasattr(app.state, 'redis') and app.state.redis:
        await app.state.redis.close()
        logger.info("Redis connection closed")
    
    logger.info("API Gateway shutdown completed")


async def _validate_upstream_services():
    """Validate connectivity to upstream services on startup."""
    import httpx
    
    services = {
        "AMS": settings.ams_base_url,
        "Letta": settings.letta_base_url,
        "LiteLLM": settings.litellm_base_url,
        "Supabase": settings.supabase_url
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, url in services.items():
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                if response.status_code == 200:
                    logger.info(f"{service_name} service is healthy")
                else:
                    logger.warning(f"{service_name} service returned {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to connect to {service_name}", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="AI Agent Platform API Gateway",
    description="Production-ready API Gateway for unified access to AI Agent Platform microservices",
    version=settings.version,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
    lifespan=lifespan
)

# Add CORS middleware
allowed_origins = settings.allowed_origins

# Ensure we have valid origins
if not allowed_origins or allowed_origins == ["*"]:
    logger.warning("CORS: Using wildcard origins - not recommended for production!")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-User-ID",
        "X-Idempotency-Key",
        "User-Agent",
        "Accept",
        "Origin",
        "Referer",
        "Accept-Language",
        "Content-Language",
        "Cache-Control",
        "X-Requested-With"
    ],
    expose_headers=["X-Request-ID", "X-Rate-Limit-Remaining", "X-Rate-Limit-Reset"],
    max_age=600  # Cache preflight response for 10 minutes
)

# Add custom middleware (order matters - last added runs first)
app.add_middleware(AuthMiddleware)
app.add_middleware(CircuitBreakerMiddleware)

if settings.enable_rate_limiting:
    app.add_middleware(RateLimitMiddleware)

# Setup exception handlers
setup_exception_handlers(app)

# Single optimized request logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log requests with timing and correlation ID."""
    import time
    import uuid
    
    # Skip logging for streaming requests to avoid buffering
    if (request.url.path.endswith("/proxy") or 
        request.url.path.endswith("/chat/completions") or
        "stream" in request.url.path or
        request.headers.get("accept") == "text/event-stream"):
        return await call_next(request)
    
    # Generate request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Start timing
    start_time = time.time()
    
    # Log request (only for non-OPTIONS requests to reduce noise)
    if request.method != "OPTIONS":
        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            user_id=getattr(request.state, 'user_id', None)
        )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Update metrics
        request_duration.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).observe(duration)
        
        request_counter.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        # Log response (only for non-OPTIONS and non-2xx responses)
        if request.method != "OPTIONS" and response.status_code >= 400:
            logger.warning(
                "Request completed with error",
                request_id=request_id,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
        
        return response
        
    except Exception as e:
        # Calculate duration
        duration = time.time() - start_time
        
        # Update error metrics
        request_counter.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=500
        ).inc()
        
        # Log error
        logger.error(
            "Request failed",
            request_id=request_id,
            error=str(e),
            duration_ms=round(duration * 1000, 2)
        )
        
        # Re-raise exception to be handled by exception handlers
        raise



# Include routers
app.include_router(system.router, tags=["System"])
app.include_router(user.router, prefix="/api/v1", tags=["User Management"])
app.include_router(letta.router, prefix="/api/v1/letta", tags=["Letta Proxy"])
app.include_router(ams.router, prefix="/api/v1/ams", tags=["AMS Proxy"])
# LLM Proxy must be registered BEFORE agents router to avoid route conflicts
app.include_router(llm_proxy.router, prefix="/api/v1/agents", tags=["LLM Proxy"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agent Management (Legacy)"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["Template Management (Legacy)"])

# Prometheus metrics endpoint
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Health check for load balancers
@app.get("/ping", include_in_schema=False)
async def ping():
    """Simple ping endpoint for load balancer health checks."""
    from datetime import datetime
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# CORS debug endpoint
@app.get("/cors-debug", include_in_schema=False)
async def cors_debug():
    """Debug endpoint to check CORS configuration."""
    return {
        "allowed_origins": settings.allowed_origins,
        "origins_str": settings.allowed_origins_str,
        "origins_count": len(settings.allowed_origins),
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


if __name__ == "__main__":
    # Run with uvicorn for development
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.environment == "development" else False,
        log_config=None,  # Use our custom logging
        access_log=False,  # We handle access logging in middleware
        server_header=False,  # Disable server header
        date_header=False  # Disable date header
    )