"""
Common Pydantic models used across the application.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, ConfigDict


class ResponseStatus(str, Enum):
    """Standard response status values."""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class ServiceStatus(str, Enum):
    """Service health status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class BaseResponse(BaseModel):
    """Base response model with common fields."""
    model_config = ConfigDict(json_encoders={datetime: lambda dt: dt.isoformat()})
    
    status: ResponseStatus
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    request_id: Optional[str] = None


class ErrorDetail(BaseModel):
    """Detailed error information."""
    code: str
    message: str
    field: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseResponse):
    """Standard error response model."""
    status: ResponseStatus = ResponseStatus.ERROR
    error: ErrorDetail
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "error",
                "message": "Validation failed",
                "timestamp": "2025-09-21T05:09:00Z",
                "request_id": "req_123456789",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid input data",
                    "field": "email",
                    "context": {"provided_value": "invalid-email"}
                }
            }
        }


class SuccessResponse(BaseResponse):
    """Standard success response model."""
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Optional[Any] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Operation completed successfully",
                "timestamp": "2025-09-21T05:09:00Z",
                "request_id": "req_123456789",
                "data": {}
            }
        }


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    page: int = Field(1, ge=1, description="Page number (1-based)")
    limit: int = Field(20, ge=1, le=100, description="Items per page")
    
    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.limit


class PaginatedResponse(BaseResponse):
    """Paginated response model."""
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: List[Any] = []
    pagination: Dict[str, Any] = Field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        items: List[Any],
        page: int,
        limit: int,
        total: int,
        request_id: Optional[str] = None
    ) -> "PaginatedResponse":
        """Create paginated response with metadata."""
        total_pages = (total + limit - 1) // limit
        
        return cls(
            data=items,
            request_id=request_id,
            pagination={
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        )


class UserContext(BaseModel):
    """User context extracted from JWT token."""
    user_id: str = Field(..., description="Unique user identifier")
    email: Optional[str] = Field(None, description="User email address")
    role: Optional[str] = Field(None, description="User role")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional user metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123456789",
                "email": "user@example.com",
                "role": "user",
                "metadata": {
                    "subscription": "pro",
                    "features": ["advanced_agents"]
                }
            }
        }


class ServiceHealth(BaseModel):
    """Individual service health status."""
    name: str = Field(..., description="Service name")
    status: ServiceStatus = Field(..., description="Service status")
    url: str = Field(..., description="Service URL")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
    last_check: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Last health check time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "AMS",
                "status": "healthy",
                "url": "https://api.example.com/ams",
                "response_time_ms": 45.2,
                "error": None,
                "last_check": "2025-09-21T05:09:00Z"
            }
        }


class RateLimitInfo(BaseModel):
    """Rate limit information."""
    limit: int = Field(..., description="Rate limit threshold")
    remaining: int = Field(..., description="Remaining requests")
    reset_time: str = Field(..., description="When the rate limit resets")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")
    
    class Config:
        json_schema_extra = {
            "example": {
                "limit": 1000,
                "remaining": 750,
                "reset_time": "2025-09-21T06:00:00Z",
                "retry_after": None
            }
        }


class IdempotencyKey(BaseModel):
    """Idempotency key for safe retries."""
    key: str = Field(..., min_length=1, max_length=255, description="Unique idempotency key")
    
    @validator('key')
    def validate_key_format(cls, v):
        """Validate idempotency key format."""
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Idempotency key must contain only alphanumeric characters, hyphens, and underscores")
        return v


class RequestMetadata(BaseModel):
    """Common request metadata."""
    user_agent: Optional[str] = Field(None, description="Client user agent")
    client_ip: Optional[str] = Field(None, description="Client IP address")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key for safe retries")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_agent": "Mozilla/5.0 (compatible; AI-Agent-Client/1.0)",
                "client_ip": "192.168.1.100",
                "correlation_id": "corr_123456789",
                "idempotency_key": "idem_987654321"
            }
        }
