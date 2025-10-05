"""
Custom exceptions and error handling utilities.
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from src.models.common import ErrorResponse, ErrorDetail
from src.utils.context import get_request_id

logger = structlog.get_logger(__name__)


class APIException(Exception):
    """Base API exception with structured error information."""
    
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.field = field
        self.context = context or {}
        super().__init__(message)


class AuthenticationError(APIException):
    """Authentication-related errors."""
    
    def __init__(self, message: str = "Authentication failed", context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            context=context
        )


class AuthorizationError(APIException):
    """Authorization-related errors."""
    
    def __init__(self, message: str = "Access denied", context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
            context=context
        )


class ValidationError(APIException):
    """Validation-related errors."""
    
    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            field=field,
            context=context
        )


class NotFoundError(APIException):
    """Resource not found errors."""
    
    def __init__(self, message: str = "Resource not found", context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            context=context
        )


class ConflictError(APIException):
    """Resource conflict errors."""
    
    def __init__(self, message: str = "Resource conflict", context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            context=context
        )


class RateLimitError(APIException):
    """Rate limiting errors."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if retry_after:
            context["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            context=context
        )


class ServiceUnavailableError(APIException):
    """Service unavailable errors."""
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        service_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if service_name:
            context["service"] = service_name
        
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            context=context
        )


class UpstreamError(APIException):
    """Upstream service errors."""
    
    def __init__(
        self,
        message: str = "Upstream service error",
        service_name: Optional[str] = None,
        upstream_status: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if service_name:
            context["service"] = service_name
        if upstream_status:
            context["upstream_status"] = upstream_status
        
        super().__init__(
            message=message,
            code="UPSTREAM_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            context=context
        )


class RequestTimeoutError(APIException):
    """Request timeout errors."""
    
    def __init__(
        self,
        message: str = "Request timeout",
        timeout_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        
        super().__init__(
            message=message,
            code="TIMEOUT",
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            context=context
        )


class CircuitBreakerError(APIException):
    """Circuit breaker open errors."""
    
    def __init__(
        self,
        message: str = "Service circuit breaker is open",
        service_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if service_name:
            context["service"] = service_name
        
        super().__init__(
            message=message,
            code="CIRCUIT_BREAKER_OPEN",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            context=context
        )


def create_error_response(
    exception: APIException,
    request_id: Optional[str] = None
) -> ErrorResponse:
    """Create standardized error response from API exception."""
    return ErrorResponse(
        message=exception.message,
        request_id=request_id or get_request_id(),
        error=ErrorDetail(
            code=exception.code,
            message=exception.message,
            field=exception.field,
            context=exception.context
        )
    )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions."""
    request_id = get_request_id()
    
    # Log the error
    logger.error(
        "API exception occurred",
        request_id=request_id,
        error_code=exc.code,
        error_message=exc.message,
        status_code=exc.status_code,
        field=exc.field,
        context=exc.context
    )
    
    # Create error response
    error_response = create_error_response(exc, request_id)
    
    # Add retry-after header for rate limit errors
    headers = {}
    if isinstance(exc, RateLimitError) and "retry_after" in exc.context:
        headers["Retry-After"] = str(exc.context["retry_after"])
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict(exclude_none=True),
        headers=headers
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    request_id = get_request_id()
    
    # Map HTTP status codes to error codes
    status_code_map = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    }
    
    error_code = status_code_map.get(exc.status_code, "HTTP_ERROR")
    
    # Log the error
    logger.error(
        "HTTP exception occurred",
        request_id=request_id,
        status_code=exc.status_code,
        detail=exc.detail
    )
    
    # Create error response
    error_response = ErrorResponse(
        message=str(exc.detail),
        request_id=request_id,
        error=ErrorDetail(
            code=error_code,
            message=str(exc.detail)
        )
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict(exclude_none=True)
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation exceptions."""
    request_id = get_request_id()
    
    # Extract validation errors
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"]) if error["loc"] else None
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input")
        })
    
    # Log the error
    logger.warning(
        "Validation error occurred",
        request_id=request_id,
        errors=errors
    )
    
    # Create error response
    error_response = ErrorResponse(
        message="Validation failed",
        request_id=request_id,
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            context={"errors": errors}
        )
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.dict(exclude_none=True)
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    request_id = get_request_id()
    
    # Log the error with full traceback
    logger.error(
        "Unexpected exception occurred",
        request_id=request_id,
        error=str(exc),
        exc_info=True
    )
    
    # Create generic error response (don't expose internal details)
    error_response = ErrorResponse(
        message="An unexpected error occurred",
        request_id=request_id,
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later."
        )
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.dict(exclude_none=True)
    )


def setup_exception_handlers(app):
    """Setup all exception handlers for the FastAPI app."""
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
