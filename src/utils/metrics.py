"""
Prometheus metrics collection and monitoring utilities.
"""

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry
from typing import Dict, Any
import time

# Create custom registry to avoid conflicts
REGISTRY = CollectorRegistry()

# Request metrics
request_counter = Counter(
    'api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status_code'],
    registry=REGISTRY
)

request_duration = Histogram(
    'api_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint', 'status_code'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY
)

# Authentication metrics
auth_counter = Counter(
    'api_auth_attempts_total',
    'Total number of authentication attempts',
    ['status'],
    registry=REGISTRY
)

jwt_validation_duration = Histogram(
    'api_jwt_validation_duration_seconds',
    'JWT validation duration in seconds',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
    registry=REGISTRY
)

# Rate limiting metrics
rate_limit_counter = Counter(
    'api_rate_limit_hits_total',
    'Total number of rate limit hits',
    ['user_id', 'endpoint'],
    registry=REGISTRY
)

# Circuit breaker metrics
circuit_breaker_counter = Counter(
    'api_circuit_breaker_events_total',
    'Total number of circuit breaker events',
    ['service', 'event_type'],
    registry=REGISTRY
)

circuit_breaker_state = Gauge(
    'api_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service'],
    registry=REGISTRY
)

# Upstream service metrics
upstream_request_counter = Counter(
    'api_upstream_requests_total',
    'Total number of upstream service requests',
    ['service', 'status_code'],
    registry=REGISTRY
)

upstream_request_duration = Histogram(
    'api_upstream_request_duration_seconds',
    'Upstream service request duration in seconds',
    ['service'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY
)

# Cache metrics
cache_operations_counter = Counter(
    'api_cache_operations_total',
    'Total number of cache operations',
    ['operation', 'cache_type', 'status'],
    registry=REGISTRY
)

cache_hit_ratio = Gauge(
    'api_cache_hit_ratio',
    'Cache hit ratio',
    ['cache_type'],
    registry=REGISTRY
)

# Connection metrics
active_connections = Gauge(
    'api_active_connections',
    'Number of active connections',
    registry=REGISTRY
)

redis_connections = Gauge(
    'api_redis_connections',
    'Number of Redis connections',
    ['pool'],
    registry=REGISTRY
)

# Application metrics
app_info = Info(
    'api_application_info',
    'Application information',
    registry=REGISTRY
)

app_uptime = Gauge(
    'api_application_uptime_seconds',
    'Application uptime in seconds',
    registry=REGISTRY
)

# Memory and performance metrics
memory_usage = Gauge(
    'api_memory_usage_bytes',
    'Memory usage in bytes',
    ['type'],
    registry=REGISTRY
)

active_requests = Gauge(
    'api_active_requests',
    'Number of active requests',
    registry=REGISTRY
)

# LLM proxy metrics
llm_requests_counter = Counter(
    'api_llm_requests_total',
    'Total number of LLM requests',
    ['model', 'user_id', 'status'],
    registry=REGISTRY
)

llm_tokens_counter = Counter(
    'api_llm_tokens_total',
    'Total number of LLM tokens processed',
    ['model', 'user_id', 'token_type'],
    registry=REGISTRY
)

llm_request_duration = Histogram(
    'api_llm_request_duration_seconds',
    'LLM request duration in seconds',
    ['model'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY
)


class MetricsCollector:
    """Utility class for collecting custom metrics."""
    
    def __init__(self):
        self.start_time = time.time()
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record request metrics."""
        request_counter.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        
        request_duration.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).observe(duration)
    
    def record_auth_attempt(self, success: bool, duration: float = None):
        """Record authentication attempt."""
        status = "success" if success else "failure"
        auth_counter.labels(status=status).inc()
        
        if duration is not None:
            jwt_validation_duration.observe(duration)
    
    def record_rate_limit_hit(self, user_id: str, endpoint: str):
        """Record rate limit hit."""
        rate_limit_counter.labels(
            user_id=user_id,
            endpoint=endpoint
        ).inc()
    
    def record_circuit_breaker_event(self, service: str, event_type: str):
        """Record circuit breaker event."""
        circuit_breaker_counter.labels(
            service=service,
            event_type=event_type
        ).inc()
    
    def set_circuit_breaker_state(self, service: str, state: str):
        """Set circuit breaker state."""
        state_map = {"closed": 0, "open": 1, "half-open": 2}
        circuit_breaker_state.labels(service=service).set(
            state_map.get(state, 0)
        )
    
    def record_upstream_request(self, service: str, status_code: int, duration: float):
        """Record upstream service request."""
        upstream_request_counter.labels(
            service=service,
            status_code=status_code
        ).inc()
        
        upstream_request_duration.labels(service=service).observe(duration)
    
    def record_cache_operation(self, operation: str, cache_type: str, hit: bool):
        """Record cache operation."""
        status = "hit" if hit else "miss"
        cache_operations_counter.labels(
            operation=operation,
            cache_type=cache_type,
            status=status
        ).inc()
    
    def update_cache_hit_ratio(self, cache_type: str, ratio: float):
        """Update cache hit ratio."""
        cache_hit_ratio.labels(cache_type=cache_type).set(ratio)
    
    def set_active_connections(self, count: int):
        """Set number of active connections."""
        active_connections.set(count)
    
    def set_redis_connections(self, pool: str, count: int):
        """Set number of Redis connections."""
        redis_connections.labels(pool=pool).set(count)
    
    def update_memory_usage(self, memory_type: str, bytes_used: int):
        """Update memory usage."""
        memory_usage.labels(type=memory_type).set(bytes_used)
    
    def increment_active_requests(self):
        """Increment active requests counter."""
        active_requests.inc()
    
    def decrement_active_requests(self):
        """Decrement active requests counter."""
        active_requests.dec()
    
    def record_llm_request(self, model: str, user_id: str, status: str, duration: float, 
                          prompt_tokens: int = 0, completion_tokens: int = 0):
        """Record LLM request metrics."""
        llm_requests_counter.labels(
            model=model,
            user_id=user_id,
            status=status
        ).inc()
        
        llm_request_duration.labels(model=model).observe(duration)
        
        if prompt_tokens > 0:
            llm_tokens_counter.labels(
                model=model,
                user_id=user_id,
                token_type="prompt"
            ).inc(prompt_tokens)
        
        if completion_tokens > 0:
            llm_tokens_counter.labels(
                model=model,
                user_id=user_id,
                token_type="completion"
            ).inc(completion_tokens)
    
    def update_uptime(self):
        """Update application uptime."""
        uptime = time.time() - self.start_time
        app_uptime.set(uptime)


# Global metrics collector instance
metrics = MetricsCollector()


def setup_metrics():
    """Initialize metrics with application info."""
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    # Set application info
    app_info.info({
        'version': settings.version,
        'environment': settings.environment,
        'name': settings.app_name
    })
    
    # Initialize gauges
    active_connections.set(0)
    active_requests.set(0)
    app_uptime.set(0)


def get_metrics_registry():
    """Get the metrics registry for Prometheus endpoint."""
    return REGISTRY


class RequestMetricsMiddleware:
    """Middleware for automatic request metrics collection."""
    
    def __init__(self):
        self.metrics = metrics
    
    async def __call__(self, request, call_next):
        """Middleware function to collect request metrics."""
        start_time = time.time()
        
        # Increment active requests
        self.metrics.increment_active_requests()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Record successful request
            self.metrics.record_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration=duration
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record failed request
            self.metrics.record_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
                duration=duration
            )
            
            raise
        
        finally:
            # Decrement active requests
            self.metrics.decrement_active_requests()
