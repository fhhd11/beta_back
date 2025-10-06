"""
Structured logging configuration with correlation IDs and performance monitoring.
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.typing import Processor


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Setup structured logging with correlation IDs and performance monitoring.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ("json" or "console")
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Configure structlog processors
    processors: list[Processor] = [
        # Filter out empty messages first
        filter_empty_messages,
        # Add correlation ID from context
        add_correlation_id,
        # Add timestamp
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        # Add caller info for errors only
        structlog.processors.CallsiteParameterAdder(
            parameters=[structlog.processors.CallsiteParameter.FILENAME,
                       structlog.processors.CallsiteParameter.FUNC_NAME,
                       structlog.processors.CallsiteParameter.LINENO]
        ),
        # Stack info for exceptions
        structlog.processors.format_exc_info,
        # Filter sensitive data
        filter_sensitive_data,
        # Final filter to remove any remaining empty entries
        filter_empty_messages,
    ]
    
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )
    
    # Suppress noisy third-party loggers
    _suppress_noisy_loggers(log_level)


def add_correlation_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation ID and context from request to log events."""
    import contextvars
    
    # Try to get request ID from context
    try:
        from src.utils.context import request_id_var
        request_id = request_id_var.get(None)
        if request_id:
            event_dict["request_id"] = request_id
    except (ImportError, LookupError):
        pass
    
    # Try to get user ID from context
    try:
        from src.utils.context import user_id_var
        user_id = user_id_var.get(None)
        if user_id:
            event_dict["user_id"] = user_id
    except (ImportError, LookupError):
        pass
    
    # Add service context
    event_dict["service"] = "api-gateway"
    
    # Add environment context
    try:
        from src.config.settings import get_settings
        settings = get_settings()
        event_dict["environment"] = settings.environment
    except:
        pass
    
    return event_dict


def filter_sensitive_data(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Filter sensitive data from log events."""
    sensitive_keys = {
        "password", "token", "secret", "key", "authorization", 
        "jwt", "api_key", "bearer", "auth", "credential"
    }
    
    def _filter_dict(data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively filter sensitive keys from dictionary."""
        filtered = {}
        for key, value in data.items():
            key_lower = key.lower()
            
            # Check if key contains sensitive information
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                filtered[key] = "***REDACTED***"
            elif isinstance(value, dict):
                filtered[key] = _filter_dict(value)
            elif isinstance(value, list):
                filtered[key] = [
                    _filter_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                filtered[key] = value
        
        return filtered
    
    # Filter the event dictionary
    return _filter_dict(event_dict)


def filter_empty_messages(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Filter out empty or whitespace-only messages and noisy patterns."""
    # Skip if event_dict is None or empty
    if not event_dict:
        return None
    
    # Check if event is empty or just whitespace
    event = event_dict.get("event", "")
    if isinstance(event, str) and not event.strip():
        return None
    
    # Filter out noisy CORS parsing messages
    if isinstance(event, str):
        if "CORS parsing:" in event or "raw origins_str=" in event:
            return None
        if "comma-separated parsed:" in event:
            return None
    
    # Only filter if ALL values are empty - be less aggressive
    has_meaningful_content = False
    for key, value in event_dict.items():
        if value is not None and str(value).strip():
            has_meaningful_content = True
            break
    
    if not has_meaningful_content:
        return None
    
    return event_dict


def _suppress_noisy_loggers(log_level: str) -> None:
    """Suppress noisy third-party loggers based on log level."""
    # Suppress these noisy loggers but keep some level of logging
    noisy_loggers = [
        "httpx", "httpcore", "uvicorn.access", "uvicorn.error",
        "asyncio", "multipart", "urllib3", "requests", "anyio", "h11"
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # More aggressive suppression for production
    if log_level in ["WARNING", "ERROR", "CRITICAL"]:
        production_loggers = [
            "fastapi", "starlette", "pydantic", "uvicorn"
        ]
        for logger_name in production_loggers:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
    
    # Don't change root logger level - let our application logs through


class PerformanceLogger:
    """Context manager for logging performance metrics."""
    
    def __init__(self, operation: str, logger: Optional[Any] = None):
        self.operation = operation
        self.logger = logger or structlog.get_logger()
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.debug(f"{self.operation} started")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        if self.start_time:
            duration = time.time() - self.start_time
            duration_ms = round(duration * 1000, 2)
            
            if exc_type:
                self.logger.error(
                    f"{self.operation} failed",
                    duration_ms=duration_ms,
                    error=str(exc_val) if exc_val else None
                )
            else:
                self.logger.info(
                    f"{self.operation} completed",
                    duration_ms=duration_ms
                )


def get_logger(name: str) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Convenience function for performance logging
def log_performance(operation: str, logger: Optional[Any] = None):
    """Decorator or context manager for performance logging."""
    return PerformanceLogger(operation, logger)
