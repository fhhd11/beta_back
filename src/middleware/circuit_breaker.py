"""
Circuit breaker middleware for upstream services with Redis state management.
"""

import time
from enum import Enum
from typing import Dict, Optional, Set, Callable, Any
from dataclasses import dataclass
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

from src.config.settings import get_settings
from src.models.common import ErrorResponse, ErrorDetail
from src.utils.cache import get_redis_client
from src.utils.metrics import metrics
from src.utils.exceptions import CircuitBreakerError, ServiceUnavailableError

logger = structlog.get_logger(__name__)

# Rate limiting for circuit breaker logs
_last_log_times: Dict[str, float] = {}
LOG_RATE_LIMIT = 30  # Log at most once every 30 seconds per service

def should_log_circuit_breaker(service_name: str) -> bool:
    """Check if we should log circuit breaker message for this service."""
    current_time = time.time()
    last_log_time = _last_log_times.get(service_name, 0)
    
    if current_time - last_log_time >= LOG_RATE_LIMIT:
        _last_log_times[service_name] = current_time
        return True
    
    return False


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    service_name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 3  # For half-open state
    timeout: float = 30.0
    sliding_window_size: int = 100  # Number of requests in sliding window
    minimum_requests: int = 10  # Minimum requests before circuit can open


class CircuitBreaker:
    """Individual circuit breaker for a service."""
    
    def __init__(self, config: CircuitBreakerConfig, redis_client=None):
        self.config = config
        self.redis_client = redis_client
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0
        self._state_change_time = time.time()
        self._request_window = []  # Sliding window of request results
    
    async def _get_redis(self):
        """Get Redis client for state persistence."""
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    async def _load_state_from_redis(self):
        """Load circuit breaker state from Redis."""
        try:
            redis = await self._get_redis()
            state_key = f"circuit_breaker:{self.config.service_name}:state"
            
            state_data = await redis.hgetall(state_key)
            if state_data:
                self._state = CircuitBreakerState(state_data.get("state", "closed"))
                self._failure_count = int(state_data.get("failure_count", 0))
                self._success_count = int(state_data.get("success_count", 0))
                self._last_failure_time = float(state_data.get("last_failure_time", 0))
                self._state_change_time = float(state_data.get("state_change_time", time.time()))
                
                logger.debug(
                    "Circuit breaker state loaded from Redis",
                    service=self.config.service_name,
                    state=self._state,
                    failure_count=self._failure_count
                )
        
        except Exception as e:
            logger.warning(
                "Failed to load circuit breaker state from Redis",
                service=self.config.service_name,
                error=str(e)
            )
    
    async def _save_state_to_redis(self):
        """Save circuit breaker state to Redis."""
        try:
            redis = await self._get_redis()
            state_key = f"circuit_breaker:{self.config.service_name}:state"
            
            state_data = {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "state_change_time": self._state_change_time
            }
            
            await redis.hset(state_key, mapping=state_data)
            await redis.expire(state_key, 3600)  # Expire after 1 hour
            
        except Exception as e:
            logger.warning(
                "Failed to save circuit breaker state to Redis",
                service=self.config.service_name,
                error=str(e)
            )
    
    def _update_request_window(self, success: bool):
        """Update sliding window with request result."""
        current_time = time.time()
        
        # Add new request result
        self._request_window.append({
            'success': success,
            'timestamp': current_time
        })
        
        # Remove old entries outside sliding window
        cutoff_time = current_time - 60  # 1 minute window
        self._request_window = [
            req for req in self._request_window 
            if req['timestamp'] > cutoff_time
        ]
        
        # Limit window size
        if len(self._request_window) > self.config.sliding_window_size:
            self._request_window = self._request_window[-self.config.sliding_window_size:]
    
    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate in sliding window."""
        if not self._request_window:
            return 0.0
        
        failures = sum(1 for req in self._request_window if not req['success'])
        return failures / len(self._request_window)
    
    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    async def can_execute(self) -> bool:
        """Check if request can be executed."""
        # Load current state from Redis
        await self._load_state_from_redis()
        
        current_time = time.time()
        
        if self._state == CircuitBreakerState.CLOSED:
            return True
        
        elif self._state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if current_time - self._last_failure_time >= self.config.recovery_timeout:
                await self._transition_to_half_open()
                return True
            return False
        
        elif self._state == CircuitBreakerState.HALF_OPEN:
            return True
        
        return False
    
    async def record_success(self):
        """Record a successful request."""
        self._update_request_window(True)
        
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            
            if self._success_count >= self.config.success_threshold:
                await self._transition_to_closed()
            else:
                await self._save_state_to_redis()
        
        elif self._state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            if self._failure_count > 0:
                self._failure_count = 0
                await self._save_state_to_redis()
        
        # Update metrics
        metrics.record_circuit_breaker_event(self.config.service_name, "success")
    
    async def record_failure(self):
        """Record a failed request."""
        self._update_request_window(False)
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitBreakerState.CLOSED:
            # Check if we have enough requests and high failure rate
            if (len(self._request_window) >= self.config.minimum_requests and 
                self._calculate_failure_rate() >= 0.5):  # 50% failure rate threshold
                await self._transition_to_open()
            elif self._failure_count >= self.config.failure_threshold:
                await self._transition_to_open()
            else:
                await self._save_state_to_redis()
        
        elif self._state == CircuitBreakerState.HALF_OPEN:
            # Go back to open on any failure
            await self._transition_to_open()
        
        # Update metrics
        metrics.record_circuit_breaker_event(self.config.service_name, "failure")
    
    async def _transition_to_open(self):
        """Transition to OPEN state."""
        self._state = CircuitBreakerState.OPEN
        self._state_change_time = time.time()
        self._success_count = 0
        
        await self._save_state_to_redis()
        
        logger.warning(
            "Circuit breaker opened",
            service=self.config.service_name,
            failure_count=self._failure_count,
            threshold=self.config.failure_threshold
        )
        
        metrics.record_circuit_breaker_event(self.config.service_name, "opened")
        metrics.set_circuit_breaker_state(self.config.service_name, "open")
    
    async def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self._state = CircuitBreakerState.HALF_OPEN
        self._state_change_time = time.time()
        self._success_count = 0
        
        await self._save_state_to_redis()
        
        logger.info(
            "Circuit breaker transitioned to half-open",
            service=self.config.service_name
        )
        
        metrics.record_circuit_breaker_event(self.config.service_name, "half_opened")
        metrics.set_circuit_breaker_state(self.config.service_name, "half_open")
    
    async def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self._state = CircuitBreakerState.CLOSED
        self._state_change_time = time.time()
        self._failure_count = 0
        self._success_count = 0
        
        await self._save_state_to_redis()
        
        logger.info(
            "Circuit breaker closed",
            service=self.config.service_name
        )
        
        metrics.record_circuit_breaker_event(self.config.service_name, "closed")
        metrics.set_circuit_breaker_state(self.config.service_name, "closed")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        await self._load_state_from_redis()
        
        return {
            "service": self.config.service_name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.config.failure_threshold,
            "success_threshold": self.config.success_threshold,
            "recovery_timeout": self.config.recovery_timeout,
            "last_failure_time": self._last_failure_time,
            "state_change_time": self._state_change_time,
            "can_execute": await self.can_execute()
        }


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """Middleware for circuit breaker pattern implementation."""
    
    def __init__(self, app, settings=None):
        super().__init__(app)
        self.settings = settings or get_settings()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._initialize_circuit_breakers()
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers for upstream services."""
        services = {
            "ams": {
                "patterns": ["/api/v1/me", "/api/v1/agents/create", "/api/v1/agents/update", "/api/v1/agents/delete", "/api/v1/templates"],
                "config": CircuitBreakerConfig(
                    service_name="ams",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                    timeout=self.settings.request_timeout
                )
            },
            "letta": {
                "patterns": ["/api/v1/letta"],
                "config": CircuitBreakerConfig(
                    service_name="letta",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                    timeout=self.settings.letta_timeout
                )
            },
            "litellm": {
                "patterns": ["/api/v1/agents/*/proxy"],
                "config": CircuitBreakerConfig(
                    service_name="litellm",
                    failure_threshold=self.settings.circuit_breaker_failure_threshold,
                    recovery_timeout=self.settings.circuit_breaker_recovery_timeout,
                    timeout=self.settings.request_timeout
                )
            }
        }
        
        for service_name, service_config in services.items():
            self.circuit_breakers[service_name] = CircuitBreaker(service_config["config"])
            
            # Initialize metrics
            metrics.set_circuit_breaker_state(service_name, "closed")
    
    async def dispatch(self, request: Request, call_next):
        """Apply circuit breaker logic to requests."""
        service_name = self._get_service_for_path(request.url.path)
        
        if service_name and service_name in self.circuit_breakers:
            circuit_breaker = self.circuit_breakers[service_name]
            
            # Check if circuit breaker allows execution
            if not await circuit_breaker.can_execute():
                # Only log if we haven't logged recently for this service
                if should_log_circuit_breaker(service_name):
                    logger.warning(
                        "Circuit breaker rejected request",
                        service=service_name,
                        path=request.url.path,
                        state=circuit_breaker.state,
                        note="Further rejections will be logged every 30 seconds"
                    )
                
                raise CircuitBreakerError(
                    f"Service {service_name} is currently unavailable",
                    service_name=service_name,
                    context={
                        "state": circuit_breaker.state.value,
                        "failure_count": circuit_breaker.failure_count
                    }
                )
            
            # Execute request and handle result
            try:
                response = await call_next(request)
                
                # Record success or failure based on status code
                if 200 <= response.status_code < 500:
                    await circuit_breaker.record_success()
                else:
                    await circuit_breaker.record_failure()
                
                return response
                
            except Exception as e:
                # Record failure for any exception
                await circuit_breaker.record_failure()
                raise
        
        else:
            # No circuit breaker for this path
            return await call_next(request)
    
    def _get_service_for_path(self, path: str) -> Optional[str]:
        """Determine which service a path belongs to."""
        service_patterns = {
            "ams": ["/api/v1/me", "/api/v1/agents/create", "/api/v1/agents/update", "/api/v1/agents/delete", "/api/v1/templates"],
            "letta": ["/api/v1/letta"],
            "litellm": ["/api/v1/agents/*/proxy"]
        }
        
        for service_name, patterns in service_patterns.items():
            for pattern in patterns:
                if self._path_matches_pattern(path, pattern):
                    return service_name
        
        return None
    
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
    
    async def get_circuit_breaker_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific circuit breaker."""
        if service_name in self.circuit_breakers:
            return await self.circuit_breakers[service_name].get_status()
        return None
    
    async def get_all_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        status = {}
        for service_name, circuit_breaker in self.circuit_breakers.items():
            status[service_name] = await circuit_breaker.get_status()
        return status
    
    async def reset_circuit_breaker(self, service_name: str) -> bool:
        """Reset a circuit breaker (admin function)."""
        if service_name in self.circuit_breakers:
            circuit_breaker = self.circuit_breakers[service_name]
            await circuit_breaker._transition_to_closed()
            
            logger.info(
                "Circuit breaker manually reset",
                service=service_name
            )
            
            return True
        return False


# Circuit breaker decorator for individual functions
def circuit_breaker(service_name: str, config: Optional[CircuitBreakerConfig] = None):
    """Decorator to apply circuit breaker pattern to individual functions."""
    def decorator(func: Callable) -> Callable:
        if config is None:
            cb_config = CircuitBreakerConfig(service_name=service_name)
        else:
            cb_config = config
        
        cb = CircuitBreaker(cb_config)
        
        async def wrapper(*args, **kwargs):
            if not await cb.can_execute():
                raise CircuitBreakerError(
                    f"Circuit breaker open for {service_name}",
                    service_name=service_name
                )
            
            try:
                result = await func(*args, **kwargs)
                await cb.record_success()
                return result
            
            except Exception as e:
                await cb.record_failure()
                raise
        
        # Add circuit breaker management methods
        wrapper.get_status = cb.get_status
        wrapper.reset = cb._transition_to_closed
        
        return wrapper
    
    return decorator


# Global circuit breaker manager instance
_circuit_breaker_middleware = None


def get_circuit_breaker_middleware() -> Optional[CircuitBreakerMiddleware]:
    """Get global circuit breaker middleware instance."""
    return _circuit_breaker_middleware


def set_circuit_breaker_middleware(middleware: CircuitBreakerMiddleware):
    """Set global circuit breaker middleware instance."""
    global _circuit_breaker_middleware
    _circuit_breaker_middleware = middleware
