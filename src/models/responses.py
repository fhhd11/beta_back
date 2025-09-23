"""
Response models for all API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from .common import BaseResponse, ResponseStatus, ServiceHealth, RateLimitInfo


class UserProfile(BaseModel):
    """User profile information."""
    user_id: str = Field(..., description="Unique user identifier")
    email: Optional[str] = Field(None, description="User email address")
    display_name: Optional[str] = Field(None, description="User display name")
    role: Optional[str] = Field(None, description="User role")
    subscription_tier: Optional[str] = Field(None, description="User subscription tier")
    litellm_key: Optional[str] = Field(None, description="User's LiteLLM API key for billing")
    letta_agent_id: Optional[str] = Field(None, description="User's Letta agent ID")
    agent_status: Optional[str] = Field(None, description="User's agent status")
    agents: List["AgentSummary"] = Field(default_factory=list, description="User's agents")
    created_at: Optional[str] = Field(None, description="Account creation timestamp")
    last_active: Optional[str] = Field(None, description="Last activity timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional user metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123456789",
                "email": "user@example.com",
                "display_name": "John Doe",
                "role": "user",
                "subscription_tier": "pro",
                "agents": [
                    {
                        "agent_id": "agent_123",
                        "name": "Support Agent",
                        "status": "active",
                        "created_at": "2025-09-21T05:09:00Z"
                    }
                ],
                "created_at": "2025-09-01T10:00:00Z",
                "last_active": "2025-09-21T05:00:00Z",
                "metadata": {
                    "features": ["advanced_agents", "analytics"],
                    "preferences": {"theme": "dark"}
                }
            }
        }


class AgentSummary(BaseModel):
    """Summary information for an agent."""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    status: str = Field(..., description="Agent status")
    model: Optional[str] = Field(None, description="LLM model used by agent")
    created_at: Optional[str] = Field(None, description="Agent creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    message_count: Optional[int] = Field(None, description="Total message count")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_123456789",
                "name": "Customer Support Agent",
                "description": "AI agent for handling customer support queries",
                "status": "active",
                "model": "gpt-4",
                "created_at": "2025-09-21T05:09:00Z",
                "updated_at": "2025-09-21T05:09:00Z",
                "message_count": 42
            }
        }


class AgentInstance(BaseModel):
    """Detailed agent information."""
    agent_id: str = Field(..., description="Unique agent identifier")
    user_id: str = Field(..., description="Owner user ID")
    name: str = Field(..., description="Agent name")
    description: Optional[str] = Field(None, description="Agent description")
    status: str = Field(..., description="Agent status")
    config: Dict[str, Any] = Field(default_factory=dict, description="Agent configuration")
    memory_summary: Optional[Dict[str, Any]] = Field(None, description="Memory summary")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Agent statistics")
    created_at: datetime = Field(..., description="Agent creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_123456789",
                "user_id": "user_123456789",
                "name": "Customer Support Agent",
                "description": "AI agent for handling customer support queries",
                "status": "active",
                "config": {
                    "model": "gpt-4",
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "system_prompt": "You are a helpful customer support agent"
                },
                "memory_summary": {
                    "core_memory_size": 1024,
                    "recall_memory_size": 512,
                    "archival_memory_size": 2048
                },
                "statistics": {
                    "total_messages": 42,
                    "avg_response_time": 1.5,
                    "success_rate": 0.95
                },
                "created_at": "2025-09-21T05:09:00Z",
                "updated_at": "2025-09-21T05:09:00Z",
                "metadata": {
                    "template_id": "template_123",
                    "version": "1.0.0"
                }
            }
        }


class LettaMessage(BaseModel):
    """Letta agent message."""
    message_id: str = Field(..., description="Unique message identifier")
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="Message timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Message metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "msg_123456789",
                "role": "assistant",
                "content": "Hello! How can I help you today?",
                "timestamp": "2025-09-21T05:09:00Z",
                "metadata": {
                    "model": "gpt-4",
                    "tokens_used": 15,
                    "response_time": 1.2
                }
            }
        }


class LettaAgent(BaseModel):
    """Letta agent information."""
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent name")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")
    memory: Optional[Dict[str, Any]] = Field(None, description="Agent memory")
    config: Optional[Dict[str, Any]] = Field(None, description="Agent configuration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "letta_agent_123",
                "name": "Support Agent",
                "created_at": "2025-09-21T05:09:00Z",
                "last_updated": "2025-09-21T05:09:00Z",
                "memory": {
                    "core": "You are a helpful customer support agent",
                    "recall": "Recent conversation context"
                },
                "config": {
                    "model": "gpt-4",
                    "temperature": 0.7
                }
            }
        }


class TemplateInfo(BaseModel):
    """Template information."""
    template_id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    version: str = Field(..., description="Template version")
    author: Optional[str] = Field(None, description="Template author")
    is_public: bool = Field(False, description="Whether template is public")
    tags: List[str] = Field(default_factory=list, description="Template tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    usage_count: Optional[int] = Field(None, description="Number of times used")
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "template_123456789",
                "name": "Customer Support Template",
                "description": "Template for customer support agents",
                "version": "1.0.0",
                "author": "user@example.com",
                "is_public": True,
                "tags": ["support", "customer-service"],
                "created_at": "2025-09-21T05:09:00Z",
                "updated_at": "2025-09-21T05:09:00Z",
                "usage_count": 25
            }
        }


class ValidationResult(BaseModel):
    """Template validation result."""
    is_valid: bool = Field(..., description="Whether template is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    schema_version: Optional[str] = Field(None, description="Template schema version")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "errors": [],
                "warnings": ["Template uses deprecated field 'old_config'"],
                "schema_version": "1.0"
            }
        }


class LLMResponse(BaseModel):
    """LLM proxy response."""
    id: str = Field(..., description="Response ID")
    model: str = Field(..., description="Model used")
    choices: List[Dict[str, Any]] = Field(..., description="Response choices")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token usage information")
    created: int = Field(..., description="Creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-123456789",
                "model": "gpt-4",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello! How can I help you today?"
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 15,
                    "total_tokens": 25
                },
                "created": 1695280140
            }
        }


class HealthResponse(BaseResponse):
    """System health response."""
    status: ResponseStatus = ResponseStatus.SUCCESS
    services: List[ServiceHealth] = Field(default_factory=list, description="Service health status")
    overall_status: str = Field(..., description="Overall system status")
    version: str = Field(..., description="API version")
    uptime: Optional[float] = Field(None, description="Uptime in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "System is healthy",
                "timestamp": "2025-09-21T05:09:00Z",
                "request_id": "req_123456789",
                "services": [
                    {
                        "name": "AMS",
                        "status": "healthy",
                        "url": "https://api.example.com/ams",
                        "response_time_ms": 45.2,
                        "error": None,
                        "last_check": "2025-09-21T05:09:00Z"
                    }
                ],
                "overall_status": "healthy",
                "version": "1.0.0",
                "uptime": 86400.0
            }
        }


class ApiInfo(BaseResponse):
    """API information response."""
    status: ResponseStatus = ResponseStatus.SUCCESS
    name: str = Field(..., description="API name")
    version: str = Field(..., description="API version")
    description: str = Field(..., description="API description")
    documentation_url: Optional[str] = Field(None, description="Documentation URL")
    endpoints: List[Dict[str, str]] = Field(default_factory=list, description="Available endpoints")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "timestamp": "2025-09-21T05:09:00Z",
                "name": "AI Agent Platform API Gateway",
                "version": "1.0.0",
                "description": "Production-ready API Gateway for unified access to AI Agent Platform microservices",
                "documentation_url": "https://api.example.com/docs",
                "endpoints": [
                    {"path": "/health", "description": "System health check"},
                    {"path": "/api/v1/me", "description": "User profile"}
                ]
            }
        }


class BulkOperationResponse(BaseResponse):
    """Bulk operation response."""
    status: ResponseStatus = ResponseStatus.SUCCESS
    total_items: int = Field(..., description="Total items processed")
    successful_items: int = Field(..., description="Successfully processed items")
    failed_items: int = Field(..., description="Failed items")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Individual results")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Bulk operation completed",
                "timestamp": "2025-09-21T05:09:00Z",
                "total_items": 10,
                "successful_items": 8,
                "failed_items": 2,
                "results": [
                    {"item_id": "item_1", "status": "success"},
                    {"item_id": "item_2", "status": "failed", "error": "Invalid data"}
                ],
                "errors": [
                    {"item_id": "item_2", "error": "Validation failed"}
                ]
            }
        }


# Update forward references
UserProfile.update_forward_refs()
AgentSummary.update_forward_refs()
