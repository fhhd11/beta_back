"""
Request models for all API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, AnyHttpUrl
import json


class CreateAgentRequest(BaseModel):
    """Request model for creating a new agent."""
    template_id: str = Field(..., description="Template ID to use for agent creation")
    version: Optional[str] = Field(None, description="Specific template version to use")
    use_latest: bool = Field(True, description="Whether to use the latest template version")
    agent_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Agent name (optional)")
    variables: Optional[Dict[str, Any]] = Field(None, description="Template variables")
    
    # Legacy fields for backward compatibility
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Agent name (deprecated, use agent_name)")
    description: Optional[str] = Field(None, max_length=1000, description="Agent description (not used by AMS)")
    config: Optional[Dict[str, Any]] = Field(None, description="Agent configuration (not used by AMS)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata (not used by AMS)")
    
    @validator('name', pre=True, always=True)
    def handle_legacy_name_field(cls, v, values):
        """Handle backward compatibility for name field."""
        if v and not values.get('agent_name'):
            values['agent_name'] = v
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "test-bot",
                "use_latest": True,
                "agent_name": "My Test Agent",
                "variables": {
                    "custom_var": "value"
                }
            }
        }


class UpgradeAgentRequest(BaseModel):
    """Request model for upgrading an agent."""
    target_version: str = Field(..., description="Target version for upgrade")
    use_latest: bool = Field(False, description="Whether to use the latest version")
    dry_run: bool = Field(False, description="Whether to perform a dry run")
    use_queue: bool = Field(False, description="Whether to queue the upgrade job")
    
    # Legacy fields for backward compatibility
    preserve_memory: bool = Field(True, description="Whether to preserve agent memory (not used by AMS)")
    backup_current: bool = Field(True, description="Whether to backup current agent state (not used by AMS)")
    config_updates: Optional[Dict[str, Any]] = Field(None, description="Configuration updates to apply (not used by AMS)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_version": "2.0.0",
                "use_latest": False,
                "dry_run": True,
                "use_queue": False
            }
        }


class SendMessageRequest(BaseModel):
    """Request model for sending a message to a Letta agent."""
    message: str = Field(..., min_length=1, max_length=10000, description="Message content")
    role: str = Field("user", description="Message role (user, system, assistant, function, tool, human, ai, persona, memory, context)")
    stream: bool = Field(False, description="Whether to stream the response")
    include_metadata: bool = Field(True, description="Whether to include response metadata")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for the message")
    
    @validator('role')
    def validate_role(cls, v):
        """Validate message role."""
        # Extended list of supported message roles for AI platforms
        allowed_roles = [
            "user", "assistant", "system",  # Standard OpenAI roles
            "function", "tool", "function_call",  # Function calling roles
            "human", "ai", "bot",  # Alternative naming conventions
            "persona", "memory", "context"  # Letta-specific roles
        ]
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {allowed_roles}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Hello, can you help me with my account?",
                "role": "user",
                "stream": False,
                "include_metadata": True,
                "context": {
                    "session_id": "session_123",
                    "user_context": "premium_user"
                }
            }
        }


class UpdateMemoryRequest(BaseModel):
    """Request model for updating agent memory."""
    memory_type: str = Field(..., description="Type of memory to update")
    content: Union[str, Dict[str, Any]] = Field(..., description="Memory content")
    operation: str = Field("update", description="Operation type (update, append, replace)")
    
    @validator('memory_type')
    def validate_memory_type(cls, v):
        """Validate memory type."""
        allowed_types = ["core", "recall", "archival", "persona"]
        if v not in allowed_types:
            raise ValueError(f"Memory type must be one of: {allowed_types}")
        return v
    
    @validator('operation')
    def validate_operation(cls, v):
        """Validate operation type."""
        allowed_operations = ["update", "append", "replace", "delete"]
        if v not in allowed_operations:
            raise ValueError(f"Operation must be one of: {allowed_operations}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "memory_type": "core",
                "content": "User prefers concise responses and technical details",
                "operation": "update"
            }
        }


class ArchivalMemoryRequest(BaseModel):
    """Request model for archival memory operations."""
    content: str = Field(..., min_length=1, max_length=5000, description="Content to archive")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    importance: Optional[int] = Field(None, ge=1, le=10, description="Importance level (1-10)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "User mentioned they work in healthcare and prefer HIPAA-compliant solutions",
                "tags": ["healthcare", "compliance", "preferences"],
                "importance": 8,
                "metadata": {
                    "source": "conversation",
                    "timestamp": "2025-09-21T05:09:00Z"
                }
            }
        }


class TemplateValidationRequest(BaseModel):
    """Request model for template validation."""
    template_content: Union[str, Dict[str, Any]] = Field(..., description="Template content to validate")
    template_format: str = Field("yaml", description="Template format (yaml, json)")
    strict_validation: bool = Field(True, description="Whether to perform strict validation")
    
    @validator('template_format')
    def validate_format(cls, v):
        """Validate template format."""
        allowed_formats = ["yaml", "json"]
        if v not in allowed_formats:
            raise ValueError(f"Template format must be one of: {allowed_formats}")
        return v
    
    @validator('template_content')
    def validate_content(cls, v, values):
        """Validate template content based on format."""
        template_format = values.get('template_format', 'yaml')
        
        if isinstance(v, str):
            # Validate string content can be parsed
            if template_format == "json":
                try:
                    json.loads(v)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON content: {e}")
            elif template_format == "yaml":
                try:
                    import yaml
                    yaml.safe_load(v)
                except Exception as e:
                    raise ValueError(f"Invalid YAML content: {e}")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_content": "name: Support Agent\ndescription: Customer support template\nconfig:\n  model: gpt-4\n  temperature: 0.7",
                "template_format": "yaml",
                "strict_validation": True
            }
        }


class PublishTemplateRequest(BaseModel):
    """Request model for publishing a template."""
    template_id: str = Field(..., description="Template ID to publish")
    version: str = Field(..., description="Version to publish")
    is_public: bool = Field(False, description="Whether template should be public")
    changelog: Optional[str] = Field(None, description="Changelog for this version")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "template_123",
                "version": "1.0.0",
                "is_public": True,
                "changelog": "Initial release with basic support features",
                "tags": ["support", "customer-service", "general"]
            }
        }


class LLMProxyRequest(BaseModel):
    """Request model for LLM proxy operations."""
    model: str = Field(..., description="LLM model to use")
    messages: List[Dict[str, Any]] = Field(..., description="Chat messages")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, ge=1, le=8000, description="Maximum tokens to generate")
    stream: bool = Field(False, description="Whether to stream the response")
    user_context: Optional[Dict[str, Any]] = Field(None, description="User context for billing")
    
    @validator('messages')
    def validate_messages(cls, v):
        """Validate message format."""
        if not v:
            raise ValueError("Messages cannot be empty")
        
        # Extended list of supported message roles for AI platforms
        allowed_roles = [
            "user", "assistant", "system",  # Standard OpenAI roles
            "function", "tool", "function_call",  # Function calling roles
            "human", "ai", "bot",  # Alternative naming conventions
            "persona", "memory", "context"  # Letta-specific roles
        ]
        
        for msg in v:
            if not isinstance(msg, dict):
                raise ValueError("Each message must be a dictionary")
            if "role" not in msg:
                raise ValueError("Each message must have 'role' field")
            if msg["role"] not in allowed_roles:
                raise ValueError(f"Message role must be one of: {allowed_roles}")
            
            # Content or tool_calls should be present (but allow empty content for some roles)
            if "content" not in msg and "tool_calls" not in msg:
                raise ValueError("Each message must have either 'content' or 'tool_calls' field")
            
            # If content is present, it should be a string or None
            if "content" in msg and msg["content"] is not None and not isinstance(msg["content"], str):
                raise ValueError("Message content must be a string or None")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": "Hello, how are you?"}
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": False,
                "user_context": {
                    "user_id": "user_123",
                    "billing_tier": "pro"
                }
            }
        }


class BulkOperationRequest(BaseModel):
    """Request model for bulk operations."""
    operation: str = Field(..., description="Operation type")
    items: List[Dict[str, Any]] = Field(..., min_items=1, max_items=100, description="Items to process")
    options: Optional[Dict[str, Any]] = Field(None, description="Operation options")
    
    @validator('items')
    def validate_items(cls, v):
        """Validate items list."""
        if len(v) > 100:
            raise ValueError("Cannot process more than 100 items in a single bulk operation")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "operation": "update_agents",
                "items": [
                    {"agent_id": "agent_1", "config": {"temperature": 0.8}},
                    {"agent_id": "agent_2", "config": {"max_tokens": 3000}}
                ],
                "options": {
                    "validate_only": False,
                    "rollback_on_error": True
                }
            }
        }
