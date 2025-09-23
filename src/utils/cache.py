"""
Redis caching utilities and cache patterns implementation.
"""

import json
import pickle
from typing import Any, Optional, Dict, Union, Callable, TypeVar
from functools import wraps
import asyncio
import hashlib
import time
from datetime import datetime, timedelta

import redis.asyncio as redis
import structlog
from pydantic import BaseModel

from src.config.settings import get_settings
from src.utils.metrics import metrics

logger = structlog.get_logger(__name__)

T = TypeVar('T')

# Global Redis client
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client connection."""
    global _redis_client
    
    if _redis_client is None:
        settings = get_settings()
        
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                db=settings.redis_db,
                max_connections=settings.redis_max_connections,
                decode_responses=True
            )
            
            # Test connection
            await _redis_client.ping()
            logger.info("Redis connection established", url=settings.redis_url)
            
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    return _redis_client


async def close_redis_client():
    """Close Redis client connection."""
    global _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


class CacheManager:
    """Advanced cache manager with multiple strategies."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.hit_counts: Dict[str, int] = {}
        self.miss_counts: Dict[str, int] = {}
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis client instance."""
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis
    
    def _serialize_value(self, value: Any) -> str:
        """Serialize value for caching."""
        if isinstance(value, BaseModel):
            return json.dumps(value.dict())
        elif isinstance(value, (dict, list, str, int, float, bool)):
            return json.dumps(value)
        else:
            # Use pickle for complex objects
            return pickle.dumps(value).hex()
    
    def _deserialize_value(self, serialized: str, value_type: type = None) -> Any:
        """Deserialize cached value."""
        try:
            # Try JSON first
            return json.loads(serialized)
        except (json.JSONDecodeError, TypeError):
            try:
                # Try pickle
                return pickle.loads(bytes.fromhex(serialized))
            except Exception:
                # Return as string if all else fails
                return serialized
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from prefix and arguments."""
        # Create a stable hash from arguments
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        try:
            redis = await self._get_redis()
            cached_data = await redis.get(key)
            
            if cached_data is not None:
                # Record cache hit
                self.hit_counts[key] = self.hit_counts.get(key, 0) + 1
                metrics.record_cache_operation("get", "redis", True)
                
                # Parse cached data
                if isinstance(cached_data, str) and cached_data.startswith('{"value":'):
                    data = json.loads(cached_data)
                    return self._deserialize_value(data["value"])
                else:
                    return self._deserialize_value(cached_data)
            
            # Record cache miss
            self.miss_counts[key] = self.miss_counts.get(key, 0) + 1
            metrics.record_cache_operation("get", "redis", False)
            return default
            
        except Exception as e:
            logger.warning("Cache get failed", key=key, error=str(e))
            metrics.record_cache_operation("get", "redis", False)
            return default
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        nx: bool = False
    ) -> bool:
        """Set value in cache with optional TTL."""
        try:
            redis = await self._get_redis()
            
            # Serialize value
            serialized_value = self._serialize_value(value)
            cache_data = {
                "value": serialized_value,
                "timestamp": time.time(),
                "ttl": ttl
            }
            
            # Set with TTL
            result = await redis.set(
                key,
                json.dumps(cache_data),
                ex=ttl,
                nx=nx
            )
            
            if result:
                metrics.record_cache_operation("set", "redis", True)
                logger.debug("Cache set successful", key=key, ttl=ttl)
            else:
                metrics.record_cache_operation("set", "redis", False)
                
            return bool(result)
            
        except Exception as e:
            logger.warning("Cache set failed", key=key, error=str(e))
            metrics.record_cache_operation("set", "redis", False)
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            redis = await self._get_redis()
            result = await redis.delete(key)
            
            if result:
                metrics.record_cache_operation("delete", "redis", True)
                # Clean up local counters
                self.hit_counts.pop(key, None)
                self.miss_counts.pop(key, None)
            else:
                metrics.record_cache_operation("delete", "redis", False)
                
            return bool(result)
            
        except Exception as e:
            logger.warning("Cache delete failed", key=key, error=str(e))
            metrics.record_cache_operation("delete", "redis", False)
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            redis = await self._get_redis()
            result = await redis.exists(key)
            return bool(result)
        except Exception as e:
            logger.warning("Cache exists check failed", key=key, error=str(e))
            return False
    
    async def increment(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> int:
        """Increment counter in cache."""
        try:
            redis = await self._get_redis()
            
            # Use pipeline for atomic operations
            async with redis.pipeline() as pipe:
                await pipe.incr(key, amount)
                if ttl:
                    await pipe.expire(key, ttl)
                results = await pipe.execute()
                
            return results[0]
            
        except Exception as e:
            logger.warning("Cache increment failed", key=key, error=str(e))
            return 0
    
    async def get_multiple(self, keys: list[str]) -> Dict[str, Any]:
        """Get multiple values from cache."""
        try:
            redis = await self._get_redis()
            values = await redis.mget(keys)
            
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    self.hit_counts[key] = self.hit_counts.get(key, 0) + 1
                    metrics.record_cache_operation("get", "redis", True)
                    result[key] = self._deserialize_value(value)
                else:
                    self.miss_counts[key] = self.miss_counts.get(key, 0) + 1
                    metrics.record_cache_operation("get", "redis", False)
            
            return result
            
        except Exception as e:
            logger.warning("Cache get_multiple failed", keys=keys, error=str(e))
            return {}
    
    async def set_multiple(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple values in cache."""
        try:
            redis = await self._get_redis()
            
            # Serialize all values
            serialized_mapping = {}
            for key, value in mapping.items():
                cache_data = {
                    "value": self._serialize_value(value),
                    "timestamp": time.time(),
                    "ttl": ttl
                }
                serialized_mapping[key] = json.dumps(cache_data)
            
            # Use pipeline for atomic operations
            async with redis.pipeline() as pipe:
                await pipe.mset(serialized_mapping)
                if ttl:
                    for key in mapping.keys():
                        await pipe.expire(key, ttl)
                await pipe.execute()
            
            metrics.record_cache_operation("set_multiple", "redis", True)
            return True
            
        except Exception as e:
            logger.warning("Cache set_multiple failed", error=str(e))
            metrics.record_cache_operation("set_multiple", "redis", False)
            return False
    
    async def get_or_set(
        self, 
        key: str, 
        factory: Callable[[], Any], 
        ttl: Optional[int] = None
    ) -> Any:
        """Get value from cache or set it using factory function."""
        # Try to get from cache first
        cached_value = await self.get(key)
        if cached_value is not None:
            return cached_value
        
        # Generate new value
        try:
            if asyncio.iscoroutinefunction(factory):
                new_value = await factory()
            else:
                new_value = factory()
            
            # Cache the new value
            await self.set(key, new_value, ttl)
            return new_value
            
        except Exception as e:
            logger.error("Cache factory function failed", key=key, error=str(e))
            raise
    
    def get_hit_ratio(self, key: str) -> float:
        """Get cache hit ratio for a specific key."""
        hits = self.hit_counts.get(key, 0)
        misses = self.miss_counts.get(key, 0)
        total = hits + misses
        
        if total == 0:
            return 0.0
        
        return hits / total
    
    def get_overall_hit_ratio(self) -> float:
        """Get overall cache hit ratio."""
        total_hits = sum(self.hit_counts.values())
        total_misses = sum(self.miss_counts.values())
        total = total_hits + total_misses
        
        if total == 0:
            return 0.0
        
        return total_hits / total
    
    async def clear_cache_pattern(self, pattern: str) -> int:
        """Clear all cache keys matching a pattern."""
        try:
            redis = await self._get_redis()
            keys = await redis.keys(pattern)
            
            if keys:
                await redis.delete(*keys)
                logger.info("Cache pattern cleared", pattern=pattern, count=len(keys))
                return len(keys)
            
            return 0
            
        except Exception as e:
            logger.warning("Cache pattern clear failed", pattern=pattern, error=str(e))
            return 0


# Global cache manager instance
cache_manager = CacheManager()


def cached(
    prefix: str,
    ttl: Optional[int] = None,
    key_generator: Optional[Callable] = None
):
    """Decorator for caching function results."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            await cache_manager.set(cache_key, result, ttl)
            return result
        
        # Add cache management methods to the wrapped function
        wrapper.cache_key = lambda *args, **kwargs: (
            key_generator(*args, **kwargs) if key_generator
            else cache_manager._generate_key(prefix, *args, **kwargs)
        )
        wrapper.invalidate = lambda *args, **kwargs: cache_manager.delete(
            wrapper.cache_key(*args, **kwargs)
        )
        
        return wrapper
    return decorator


# Pre-configured cache decorators for common use cases
def cached_user_profile(ttl: int = 300):
    """Cache user profile data for 5 minutes by default."""
    return cached("user_profile", ttl=ttl)


def cached_agent_ownership(ttl: int = 600):
    """Cache agent ownership data for 10 minutes by default."""
    return cached("agent_ownership", ttl=ttl)


def cached_jwt_validation(ttl: int = 300):
    """Cache JWT validation results for 5 minutes by default."""
    return cached("jwt_validation", ttl=ttl)


def cached_health_check(ttl: int = 60):
    """Cache health check results for 1 minute by default."""
    return cached("health_check", ttl=ttl)


# Utility functions
async def warm_cache(cache_keys: Dict[str, Callable], ttl: Optional[int] = None):
    """Warm up cache with predefined data."""
    logger.info("Starting cache warm-up", keys=list(cache_keys.keys()))
    
    for key, factory in cache_keys.items():
        try:
            if asyncio.iscoroutinefunction(factory):
                value = await factory()
            else:
                value = factory()
            
            await cache_manager.set(key, value, ttl)
            logger.debug("Cache warmed", key=key)
            
        except Exception as e:
            logger.warning("Cache warm-up failed", key=key, error=str(e))
    
    logger.info("Cache warm-up completed")


async def clear_cache_pattern(pattern: str):
    """Clear all cache keys matching a pattern."""
    try:
        redis = await get_redis_client()
        keys = await redis.keys(pattern)
        
        if keys:
            await redis.delete(*keys)
            logger.info("Cache pattern cleared", pattern=pattern, count=len(keys))
        
    except Exception as e:
        logger.warning("Cache pattern clear failed", pattern=pattern, error=str(e))
