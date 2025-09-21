"""
System endpoints for health checks, API information, and documentation.
"""

import time
import asyncio
from typing import Dict, List
from fastapi import APIRouter, Request, Depends
import httpx
import structlog

from src.config.settings import get_settings
from src.models.common import ServiceHealth, ServiceStatus
from src.models.responses import HealthResponse, ApiInfo
from src.utils.cache import cache_manager, cached_health_check
from src.utils.metrics import metrics
from src.middleware.circuit_breaker import get_circuit_breaker_middleware

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
    description="Check the health status of all upstream services and system components"
)
async def health_check(request: Request):
    """
    Comprehensive health check endpoint that verifies:
    - Upstream service availability (AMS, Letta, LiteLLM, Supabase)
    - Redis connectivity
    - Circuit breaker status
    - System resource usage
    """
    settings = get_settings()
    start_time = time.time()
    
    # Check all services in parallel
    service_checks = await asyncio.gather(
        _check_ams_health(settings),
        _check_letta_health(settings),
        _check_litellm_health(settings),
        _check_supabase_health(settings),
        _check_redis_health(),
        return_exceptions=True
    )
    
    services = []
    overall_healthy = True
    
    # Process service check results
    service_names = ["AMS", "Letta", "LiteLLM", "Supabase", "Redis"]
    for i, result in enumerate(service_checks):
        if isinstance(result, ServiceHealth):
            services.append(result)
            if result.status != ServiceStatus.HEALTHY:
                overall_healthy = False
        else:
            # Handle exceptions
            services.append(ServiceHealth(
                name=service_names[i],
                status=ServiceStatus.UNHEALTHY,
                url="unknown",
                error=str(result) if result else "Unknown error"
            ))
            overall_healthy = False
    
    # Check circuit breaker status
    circuit_breaker_status = await _get_circuit_breaker_status()
    if circuit_breaker_status:
        for service_name, status in circuit_breaker_status.items():
            if status["state"] == "open":
                overall_healthy = False
    
    # Calculate total response time
    total_time = time.time() - start_time
    
    # Determine overall status
    overall_status = "healthy" if overall_healthy else "degraded"
    
    # Update metrics
    metrics.update_uptime()
    
    logger.info(
        "Health check completed",
        overall_status=overall_status,
        response_time_ms=round(total_time * 1000, 2),
        services_count=len(services)
    )
    
    return HealthResponse(
        message=f"System is {overall_status}",
        services=services,
        overall_status=overall_status,
        version=settings.version,
        uptime=None  # Will be calculated differently
    )


@cached_health_check(ttl=30)  # Cache for 30 seconds
async def _check_ams_health(settings) -> ServiceHealth:
    """Check AMS service health."""
    return await _check_service_health(
        name="AMS",
        url=f"{settings.ams_base_url}/health",
        timeout=5.0
    )


@cached_health_check(ttl=30)
async def _check_letta_health(settings) -> ServiceHealth:
    """Check Letta service health."""
    return await _check_service_health(
        name="Letta",
        url=f"{settings.letta_base_url}/health",
        timeout=5.0
    )


@cached_health_check(ttl=30)
async def _check_litellm_health(settings) -> ServiceHealth:
    """Check LiteLLM service health."""
    return await _check_service_health(
        name="LiteLLM",
        url=f"{settings.litellm_base_url}/health",
        timeout=5.0
    )


@cached_health_check(ttl=30)
async def _check_supabase_health(settings) -> ServiceHealth:
    """Check Supabase service health."""
    return await _check_service_health(
        name="Supabase",
        url=f"{settings.supabase_url}/health",
        timeout=5.0
    )


async def _check_redis_health() -> ServiceHealth:
    """Check Redis connectivity."""
    start_time = time.time()
    
    try:
        # Test Redis connection with a simple ping
        redis_client = await cache_manager._get_redis()
        await redis_client.ping()
        
        response_time = (time.time() - start_time) * 1000
        
        return ServiceHealth(
            name="Redis",
            status=ServiceStatus.HEALTHY,
            url="redis://redis:6379",
            response_time_ms=response_time
        )
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        
        return ServiceHealth(
            name="Redis",
            status=ServiceStatus.UNHEALTHY,
            url="redis://redis:6379",
            response_time_ms=response_time,
            error=str(e)
        )


async def _check_service_health(name: str, url: str, timeout: float = 5.0) -> ServiceHealth:
    """Generic service health check."""
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                status = ServiceStatus.HEALTHY
                error = None
            elif 200 <= response.status_code < 500:
                status = ServiceStatus.DEGRADED
                error = f"HTTP {response.status_code}"
            else:
                status = ServiceStatus.UNHEALTHY
                error = f"HTTP {response.status_code}"
            
            return ServiceHealth(
                name=name,
                status=status,
                url=url,
                response_time_ms=response_time,
                error=error
            )
            
    except httpx.TimeoutException:
        response_time = timeout * 1000
        return ServiceHealth(
            name=name,
            status=ServiceStatus.UNHEALTHY,
            url=url,
            response_time_ms=response_time,
            error="Request timeout"
        )
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceHealth(
            name=name,
            status=ServiceStatus.UNHEALTHY,
            url=url,
            response_time_ms=response_time,
            error=str(e)
        )


async def _get_circuit_breaker_status() -> Dict[str, Dict]:
    """Get circuit breaker status for all services."""
    try:
        circuit_breaker_middleware = get_circuit_breaker_middleware()
        if circuit_breaker_middleware:
            return await circuit_breaker_middleware.get_all_circuit_breaker_status()
    except Exception as e:
        logger.warning("Failed to get circuit breaker status", error=str(e))
    
    return {}


@router.get(
    "/",
    response_model=ApiInfo,
    summary="API Information",
    description="Get basic information about the API Gateway including version and available endpoints"
)
async def api_info():
    """
    Get API Gateway information including:
    - Service name and version
    - Available endpoints
    - Documentation links
    - System capabilities
    """
    settings = get_settings()
    
    # Define available endpoints
    endpoints = [
        {"path": "/health", "description": "System health check"},
        {"path": "/api/v1/me", "description": "User profile information"},
        {"path": "/api/v1/letta/*", "description": "Letta agent proxy"},
        {"path": "/api/v1/agents", "description": "Agent management"},
        {"path": "/api/v1/templates", "description": "Template management"},
        {"path": "/api/v1/agents/{user_id}/proxy", "description": "LLM proxy for agents"},
        {"path": "/docs", "description": "Interactive API documentation"},
        {"path": "/metrics", "description": "Prometheus metrics"}
    ]
    
    documentation_url = None
    if settings.enable_docs:
        # Construct documentation URL (assuming we're behind a reverse proxy or have a known host)
        documentation_url = "/docs"
    
    return ApiInfo(
        name=settings.app_name,
        version=settings.version,
        description="Production-ready API Gateway for unified access to AI Agent Platform microservices",
        documentation_url=documentation_url,
        endpoints=endpoints
    )


@router.get(
    "/status",
    summary="Detailed System Status",
    description="Get detailed system status including metrics, circuit breakers, and performance data"
)
async def detailed_status(request: Request):
    """
    Get comprehensive system status including:
    - Service health details
    - Circuit breaker states
    - Performance metrics
    - Cache statistics
    - Rate limiting status
    """
    settings = get_settings()
    
    # Get basic health info
    health_response = await health_check(request)
    
    # Get circuit breaker status
    circuit_breaker_status = await _get_circuit_breaker_status()
    
    # Get cache statistics
    cache_stats = {
        "hit_ratio": cache_manager.get_overall_hit_ratio(),
        "redis_connected": True  # We'll assume connected if health check passed
    }
    
    # Get system metrics
    system_metrics = {
        "active_connections": metrics.active_connections._value._value if hasattr(metrics.active_connections, '_value') else 0,
        "active_requests": metrics.active_requests._value._value if hasattr(metrics.active_requests, '_value') else 0,
        "uptime_seconds": metrics.app_uptime._value._value if hasattr(metrics.app_uptime, '_value') else 0
    }
    
    # Compile comprehensive status
    status = {
        "timestamp": health_response.timestamp,
        "version": settings.version,
        "environment": settings.environment,
        "overall_status": health_response.overall_status,
        "services": [service.dict() for service in health_response.services],
        "circuit_breakers": circuit_breaker_status,
        "cache": cache_stats,
        "metrics": system_metrics,
        "features": {
            "rate_limiting": settings.enable_rate_limiting,
            "caching": settings.enable_caching,
            "metrics": settings.enable_metrics,
            "docs": settings.enable_docs
        }
    }
    
    return status


@router.post(
    "/admin/circuit-breaker/{service_name}/reset",
    summary="Reset Circuit Breaker",
    description="Reset a circuit breaker for a specific service (admin only)"
)
async def reset_circuit_breaker(service_name: str):
    """
    Reset circuit breaker for a specific service.
    This is an admin endpoint that should be protected in production.
    """
    circuit_breaker_middleware = get_circuit_breaker_middleware()
    
    if not circuit_breaker_middleware:
        return {"error": "Circuit breaker middleware not available"}
    
    success = await circuit_breaker_middleware.reset_circuit_breaker(service_name)
    
    if success:
        logger.info("Circuit breaker reset via admin endpoint", service=service_name)
        return {"message": f"Circuit breaker for {service_name} has been reset"}
    else:
        return {"error": f"Service {service_name} not found or reset failed"}


@router.get(
    "/admin/circuit-breakers",
    summary="Get All Circuit Breaker Status",
    description="Get status of all circuit breakers (admin only)"
)
async def get_all_circuit_breakers():
    """
    Get detailed status of all circuit breakers.
    This is an admin endpoint that should be protected in production.
    """
    circuit_breaker_status = await _get_circuit_breaker_status()
    return {"circuit_breakers": circuit_breaker_status}
