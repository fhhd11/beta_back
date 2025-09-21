"""
Application settings and configuration management.
Environment-based configuration with Pydantic Settings validation.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator, AnyHttpUrl
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
    
    # Performance settings
    max_concurrent_requests: int = 1000
    request_timeout: float = 30.0
    letta_timeout: float = 60.0
    
    # Feature flags
    enable_rate_limiting: bool = True
    enable_caching: bool = True
    enable_metrics: bool = True
    enable_docs: bool = True
    
    # CORS configuration
    allowed_origins: List[str] = ["*"]
    
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
    
    @validator("allowed_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level setting."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of: {allowed}")
        return v.upper()
    
    @validator("supabase_jwt_secret")
    def validate_jwt_secret(cls, v):
        """Validate JWT secret is provided and has minimum length."""
        if not v:
            raise ValueError("Supabase JWT secret is required")
        # Allow shorter secrets for development/testing
        if len(v) < 10:
            raise ValueError("Supabase JWT secret must be at least 10 characters long")
        return v
    
    @validator("supabase_service_key")
    def validate_service_key(cls, v):
        """Validate Supabase service key is provided."""
        if not v:
            # Allow placeholder for development
            return "supabase-service-key-placeholder"
        return v
    
    @validator("letta_api_key")
    def validate_letta_key(cls, v):
        """Validate Letta API key is provided."""
        if not v:
            # Allow placeholder for development
            return "letta-dev-placeholder"
        return v
    
    @validator("agent_secret_master_key")
    def validate_agent_secret(cls, v):
        """Validate Agent Secret Master Key is provided."""
        if not v:
            # Allow placeholder for development
            return "dev-agent-secret-placeholder"
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
    
    model_config = {
        "case_sensitive": False,
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings instance."""
    return Settings()


# Export settings instance for convenient imports
settings = get_settings()
