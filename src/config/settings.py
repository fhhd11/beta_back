"""
Application settings and configuration management.
Environment-based configuration with Pydantic Settings validation.
"""

from functools import lru_cache
from typing import List, Optional, Union, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator, AnyHttpUrl, Field
import os


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application info
    app_name: str = "AI Agent Platform API Gateway"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    
    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # Service URLs - Required
    ams_base_url: AnyHttpUrl
    letta_base_url: AnyHttpUrl
    litellm_base_url: AnyHttpUrl
    supabase_url: AnyHttpUrl
    
    # Authentication - Required
    supabase_jwt_secret: str
    supabase_service_key: str
    letta_api_key: str
    agent_secret_master_key: str
    
    # LiteLLM configuration (optional, only needed for admin operations)
    litellm_master_key: Optional[str] = Field(default=None, description="LiteLLM master key for admin operations")
    
    # Admin panel authentication
    admin_secret_key: str = Field(default="change-me-in-production", description="Secret key for admin panel access")
    
    # Performance settings
    max_concurrent_requests: int = 1000
    request_timeout: float = 30.0
    letta_timeout: float = 60.0
    
    # HTTP client settings
    http_max_connections: int = 200
    http_max_keepalive_connections: int = 50
    http_keepalive_expiry: float = 30.0
    http_connect_timeout: float = 5.0
    http_read_timeout: float = 30.0
    http_write_timeout: float = 5.0
    http_pool_timeout: float = 10.0
    
    # Streaming settings
    stream_chunk_size: int = 512
    stream_keepalive_interval: int = 30
    stream_buffer_size: int = 8192
    
    # Feature flags
    enable_rate_limiting: bool = True
    enable_caching: bool = True
    enable_metrics: bool = True
    enable_docs: bool = True
    
    # CORS configuration
    allowed_origins_str: str = Field(default="*", description="Allowed CORS origins (comma-separated or JSON array)", alias="ALLOWED_ORIGINS")
    
    # Redis configuration
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_max_connections: int = 10
    
    # Rate limiting configuration
    rate_limit_general: int = 1000  # requests per hour per user
    rate_limit_llm: int = 100      # LLM requests per hour per user
    rate_limit_proxy: int = 500    # LiteLLM proxy requests per hour per user
    
    # Cache TTL settings (in seconds)
    cache_ttl_jwt: int = 300       # 5 minutes
    cache_ttl_user: int = 300      # 5 minutes
    cache_ttl_ownership: int = 600 # 10 minutes
    cache_ttl_health: int = 60     # 1 minute
    
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    circuit_breaker_success_threshold: int = 3
    circuit_breaker_sliding_window_size: int = 100
    circuit_breaker_minimum_requests: int = 10
    circuit_breaker_expected_exception: tuple = (Exception,)
    
    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security settings
    jwt_algorithm: str = "HS256"
    jwt_audience: Optional[str] = "authenticated"  # Supabase default audience
    jwt_issuer: Optional[str] = None
    
    # Request size limits
    max_request_size: int = 1048576  # 1MB
    max_template_size: int = 1048576 # 1MB for template content
    
    # Monitoring settings
    metrics_path: str = "/metrics"
    health_check_path: str = "/health"
    
    @property
    def allowed_origins(self) -> List[str]:
        """Parse and return CORS origins as a list."""
        origins_str = self.allowed_origins_str
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"CORS parsing: raw origins_str='{origins_str}', type={type(origins_str)}")
        
        # Handle None or empty string
        if not origins_str or origins_str.strip() == "":
            logger.warning("CORS parsing: empty origins_str, using wildcard")
            return ["*"]
        
        if isinstance(origins_str, str):
            # Handle potential JSON-like strings
            if origins_str.startswith('[') and origins_str.endswith(']'):
                try:
                    import json
                    parsed = json.loads(origins_str)
                    logger.info(f"CORS parsing: JSON parsed successfully: {parsed}")
                    return parsed
                except json.JSONDecodeError:
                    logger.warning(f"CORS parsing: JSON parsing failed, treating as comma-separated")
                    # If JSON parsing fails, treat as comma-separated
                    pass
            
            # Parse as comma-separated string
            parsed = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
            logger.info(f"CORS parsing: comma-separated parsed: {parsed}")
            
            # Ensure we have at least one origin
            if not parsed:
                logger.warning("CORS parsing: no valid origins found, using wildcard")
                return ["*"]
            
            return parsed
        else:
            # If it's already a list (shouldn't happen with env vars, but just in case)
            result = origins_str if isinstance(origins_str, list) else ["*"]
            logger.info(f"CORS parsing: already a list or fallback: {result}")
            return result
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level setting."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of: {allowed}")
        return v.upper()
    
    @field_validator("supabase_jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v):
        """Validate JWT secret is provided and has minimum length."""
        if not v:
            raise ValueError("Supabase JWT secret is required")
        # Allow shorter secrets for development/testing
        if len(v) < 10:
            raise ValueError("Supabase JWT secret must be at least 10 characters long")
        return v
    
    @field_validator("supabase_service_key")
    @classmethod
    def validate_service_key(cls, v):
        """Validate Supabase service key is provided."""
        if not v:
            # Allow placeholder for development
            return "supabase-service-key-placeholder"
        return v
    
    @field_validator("letta_api_key")
    @classmethod
    def validate_letta_key(cls, v):
        """Validate Letta API key is provided."""
        if not v:
            # Allow placeholder for development
            return "letta-dev-placeholder"
        return v
    
    @field_validator("agent_secret_master_key")
    @classmethod
    def validate_agent_secret(cls, v):
        """Validate Agent Secret Master Key is provided."""
        if not v:
            # Allow placeholder for development
            return "dev-agent-secret-placeholder"
        return v
    
    @field_validator("admin_secret_key")
    @classmethod
    def validate_admin_secret(cls, v):
        """Validate Admin Secret Key is provided and secure."""
        if not v:
            raise ValueError("Admin secret key is required")
        if v == "change-me-in-production":
            # Allow in development but warn
            import logging
            logging.getLogger(__name__).warning("Using default admin secret key - change this in production!")
        elif len(v) < 12:
            raise ValueError("Admin secret key must be at least 12 characters long for security")
        return v
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    @property
    def redis_connection_kwargs(self) -> dict:
        """Get Redis connection parameters."""
        return {
            "url": self.redis_url,
            "password": self.redis_password,
            "db": self.redis_db,
            "max_connections": self.redis_max_connections,
            "decode_responses": True
        }
    
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="None",
        env_prefix=""
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings instance."""
    return Settings()


# Export settings instance for convenient imports
settings = get_settings()
