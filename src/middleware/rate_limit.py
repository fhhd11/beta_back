"""
Redis-based rate limiting middleware with sliding window implementation.
"""

import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

from src.config.settings import get_settings
from src.models.common import ErrorResponse, ErrorDetail, RateLimitInfo
from src.utils.cache import get_redis_client
from src.utils.metrics import metrics
from src.utils.exceptions import RateLimitError
from src.middleware.auth import get_current_user_id

logger = structlog.get_logger(__name__)

# Rate limit categories with different limits
RATE_LIMIT_CATEGORIES = {
    "general": {
        "paths": ["/api/v1/me", "/api/v1/agents", "/api/v1/templates"],
        "limit_key": "rate_limit_general"
    },
    "llm": {
        "paths": ["/api/v1/letta", "/api/v1/agents/*/messages"],
        "limit_key": "rate_limit_llm"
    },
    "proxy": {
        "paths": ["/api/v1/agents/*/proxy"],
        "limit_key": "rate_limit_proxy"
    }
}

# Exempt endpoints from rate limiting
RATE_LIMIT_EXEMPT_PATHS = {
    "/",
    "/health",
    "/ping",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics"
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based rate limiting with sliding window algorithm."""
    
    def __init__(self, app, settings=None):
        super().__init__(app)
        self.settings = settings or get_settings()
        self.window_size = 3600  # 1 hour in seconds
        self.redis_client = None
    
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to incoming requests."""
        # Skip rate limiting if disabled
        if not self.settings.enable_rate_limiting:
            return await call_next(request)
        
        # Skip exempt paths
        if self._is_exempt_path(request.url.path):
            return await call_next(request)
        
        try:
            # Get rate limit info
            rate_limit_info = await self._check_rate_limit(request)
            
            if rate_limit_info.remaining <= 0:
                # Rate limit exceeded
                metrics.record_rate_limit_hit(
                    user_id=self._get_user_identifier(request),
                    endpoint=request.url.path
                )
                
                raise RateLimitError(
                    "Rate limit exceeded",
                    retry_after=rate_limit_info.retry_after,
                    context={
                        "limit": rate_limit_info.limit,
                        "remaining": rate_limit_info.remaining,
                        "reset_time": rate_limit_info.reset_time.isoformat(),
                        "retry_after": rate_limit_info.retry_after
                    }
                )
            
            # Continue with request
            response = await call_next(request)
            
            # Add rate limit headers to response
            self._add_rate_limit_headers(response, rate_limit_info)
            
            return response
            
        except RateLimitError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=ErrorResponse(
                    message=e.message,
                    request_id=getattr(request.state, 'request_id', None),
                    error=ErrorDetail(
                        code=e.code,
                        message=e.message,
                        context=e.context
                    )
                ).dict(exclude_none=True),
                headers={
                    "Retry-After": str(e.context.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(e.context.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": e.context.get("reset_time", "")
                }
            )
        
        except Exception as e:
            logger.error("Rate limiting error", error=str(e), exc_info=True)
            # Continue without rate limiting on error
            return await call_next(request)
    
    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        return any(path.startswith(exempt_path) or path == exempt_path 
                  for exempt_path in RATE_LIMIT_EXEMPT_PATHS)
    
    def _get_user_identifier(self, request: Request) -> str:
        """Get user identifier for rate limiting."""
        try:
            # Try to get authenticated user ID
            return get_current_user_id(request)
        except Exception:
            # Fall back to IP address for unauthenticated requests
            client_ip = request.client.host if request.client else "unknown"
            return f"ip:{client_ip}"
    
    def _get_rate_limit_category(self, path: str) -> str:
        """Determine rate limit category for the path."""
        for category, config in RATE_LIMIT_CATEGORIES.items():
            for pattern in config["paths"]:
                if self._path_matches_pattern(path, pattern):
                    return category
        
        return "general"  # Default category
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern with wildcard support."""
        if "*" not in pattern:
            return path.startswith(pattern)
        
        # Simple wildcard matching
        pattern_parts = pattern.split("*")
        if len(pattern_parts) == 2:
            prefix, suffix = pattern_parts
            return path.startswith(prefix) and path.endswith(suffix)
        
        return False
    
    def _get_rate_limit_for_category(self, category: str) -> int:
        """Get rate limit value for category."""
        if category not in RATE_LIMIT_CATEGORIES:
            category = "general"
        
        limit_key = RATE_LIMIT_CATEGORIES[category]["limit_key"]
        return getattr(self.settings, limit_key, 1000)
    
    async def _check_rate_limit(self, request: Request) -> RateLimitInfo:
        """Check rate limit using sliding window algorithm."""
        user_id = self._get_user_identifier(request)
        category = self._get_rate_limit_category(request.url.path)
        limit = self._get_rate_limit_for_category(category)
        
        # Create Redis key
        redis_key = f"rate_limit:{category}:{user_id}"
        
        # Get current time
        now = time.time()
        window_start = now - self.window_size
        
        # Get Redis client
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        
        try:
            # Use Redis pipeline for atomic operations
            async with self.redis_client.pipeline() as pipe:
                # Remove old entries outside the window
                await pipe.zremrangebyscore(redis_key, 0, window_start)
                
                # Count current requests in window
                await pipe.zcard(redis_key)
                
                # Add current request
                await pipe.zadd(redis_key, {str(now): now})
                
                # Set expiry for the key
                await pipe.expire(redis_key, self.window_size + 60)
                
                # Execute pipeline
                results = await pipe.execute()
                
                current_count = results[1]  # Count after removing old entries
            
            # Calculate remaining requests
            remaining = max(0, limit - current_count - 1)  # -1 for current request
            
            # Calculate reset time (next window)
            reset_time = datetime.fromtimestamp(now + self.window_size).isoformat()
            
            # Calculate retry after (time until window slides enough)
            if remaining <= 0:
                # Find the oldest request in current window
                oldest_requests = await self.redis_client.zrange(
                    redis_key, 0, 0, withscores=True
                )
                
                if oldest_requests:
                    oldest_timestamp = oldest_requests[0][1]
                    retry_after = int(oldest_timestamp + self.window_size - now) + 1
                else:
                    retry_after = 60  # Default retry after
            else:
                retry_after = None
            
            logger.debug(
                "Rate limit check",
                user_id=user_id,
                category=category,
                current_count=current_count,
                limit=limit,
                remaining=remaining
            )
            
            return RateLimitInfo(
                limit=limit,
                remaining=remaining,
                reset_time=reset_time,
                retry_after=retry_after
            )
            
        except Exception as e:
            logger.error("Redis rate limit check failed", error=str(e))
            
            # Return permissive rate limit info on Redis failure
            return RateLimitInfo(
                limit=limit,
                remaining=limit - 1,
                reset_time=datetime.fromtimestamp(now + self.window_size).isoformat(),
                retry_after=None
            )
    
    def _add_rate_limit_headers(self, response: Response, rate_limit_info: RateLimitInfo):
        """Add rate limit headers to response."""
        response.headers["X-RateLimit-Limit"] = str(rate_limit_info.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(rate_limit_info.reset_time.timestamp()))
        
        if rate_limit_info.retry_after:
            response.headers["Retry-After"] = str(rate_limit_info.retry_after)


class RateLimitManager:
    """Utility class for managing rate limits programmatically."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.redis_client = None
    
    async def _get_redis(self):
        """Get Redis client."""
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    async def get_rate_limit_status(self, user_id: str, category: str = "general") -> RateLimitInfo:
        """Get current rate limit status for user."""
        redis_key = f"rate_limit:{category}:{user_id}"
        limit = self._get_limit_for_category(category)
        
        now = time.time()
        window_start = now - 3600  # 1 hour window
        
        try:
            redis = await self._get_redis()
            
            # Remove old entries and count current
            async with redis.pipeline() as pipe:
                await pipe.zremrangebyscore(redis_key, 0, window_start)
                await pipe.zcard(redis_key)
                results = await pipe.execute()
                
                current_count = results[1]
            
            remaining = max(0, limit - current_count)
            reset_time = datetime.fromtimestamp(now + 3600).isoformat()
            
            return RateLimitInfo(
                limit=limit,
                remaining=remaining,
                reset_time=reset_time,
                retry_after=None
            )
            
        except Exception as e:
            logger.error("Failed to get rate limit status", error=str(e))
            
            # Return default status on error
            return RateLimitInfo(
                limit=limit,
                remaining=limit,
                reset_time=datetime.fromtimestamp(now + 3600).isoformat(),
                retry_after=None
            )
    
    async def reset_rate_limit(self, user_id: str, category: str = "general") -> bool:
        """Reset rate limit for user (admin function)."""
        redis_key = f"rate_limit:{category}:{user_id}"
        
        try:
            redis = await self._get_redis()
            await redis.delete(redis_key)
            
            logger.info(
                "Rate limit reset",
                user_id=user_id,
                category=category
            )
            
            return True
            
        except Exception as e:
            logger.error("Failed to reset rate limit", error=str(e))
            return False
    
    async def set_custom_limit(
        self, 
        user_id: str, 
        category: str, 
        limit: int, 
        duration: int = 3600
    ) -> bool:
        """Set custom rate limit for user."""
        redis_key = f"rate_limit_custom:{category}:{user_id}"
        
        try:
            redis = await self._get_redis()
            await redis.setex(redis_key, duration, limit)
            
            logger.info(
                "Custom rate limit set",
                user_id=user_id,
                category=category,
                limit=limit,
                duration=duration
            )
            
            return True
            
        except Exception as e:
            logger.error("Failed to set custom rate limit", error=str(e))
            return False
    
    def _get_limit_for_category(self, category: str) -> int:
        """Get rate limit for category."""
        if category not in RATE_LIMIT_CATEGORIES:
            category = "general"
        
        limit_key = RATE_LIMIT_CATEGORIES[category]["limit_key"]
        return getattr(self.settings, limit_key, 1000)
    
    async def get_rate_limit_stats(self) -> Dict[str, any]:
        """Get overall rate limiting statistics."""
        try:
            redis = await self._get_redis()
            
            # Get all rate limit keys
            keys = await redis.keys("rate_limit:*")
            
            stats = {
                "total_users": len(set(key.split(":")[-1] for key in keys)),
                "categories": {},
                "active_limits": len(keys)
            }
            
            # Count by category
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 3:
                    category = parts[1]
                    if category not in stats["categories"]:
                        stats["categories"][category] = 0
                    stats["categories"][category] += 1
            
            return stats
            
        except Exception as e:
            logger.error("Failed to get rate limit stats", error=str(e))
            return {"error": str(e)}
