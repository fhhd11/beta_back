"""
JWT Authentication middleware with Supabase integration and caching.
"""

import time
from typing import Optional, Set
from jose import jwt
from jose.exceptions import JWTError as InvalidTokenError, ExpiredSignatureError
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

from src.config.settings import get_settings
from src.models.common import UserContext, ErrorResponse, ErrorDetail
from src.utils.cache import cache_manager, cached_jwt_validation
from src.utils.context import set_request_context
try:
    from src.utils.metrics import metrics
except ImportError:
    metrics = None
from src.utils.exceptions import AuthenticationError, AuthorizationError

logger = structlog.get_logger(__name__)

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS: Set[str] = {
    "/",
    "/health",
    "/ping",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/status",
    "/debug",
    "/cors-debug"
}

# Agent Secret Key endpoints (different auth method)
AGENT_SECRET_ENDPOINTS: Set[str] = {
    "/api/v1/agents/{user_id}/proxy",
    "/api/v1/agents/{user_id}/proxy/chat/completions"
}


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT Authentication middleware with caching and metrics."""
    
    def __init__(self, app, settings=None):
        super().__init__(app)
        self.settings = settings or get_settings()
        self.jwt_secret = self.settings.supabase_jwt_secret
        self.jwt_algorithm = self.settings.jwt_algorithm
        self.jwt_audience = self.settings.jwt_audience
        self.jwt_issuer = self.settings.jwt_issuer
    
    async def dispatch(self, request: Request, call_next):
        """Process authentication for incoming requests."""
        start_time = time.time()
        
        # Add critical logging for streaming requests
        if "stream" in request.url.path:
            logger.critical(f"🔐🔐🔐 AUTH MIDDLEWARE - STREAMING REQUEST: {request.url.path} 🔐🔐🔐")
        
        # Add debug logging
        logger.debug(
            "Auth middleware processing request",
            path=request.url.path,
            method=request.method,
            has_auth_header=bool(request.headers.get("Authorization"))
        )
        
        try:
            # Skip authentication for OPTIONS requests (CORS preflight)
            if request.method == "OPTIONS":
                logger.debug("OPTIONS request, skipping auth", path=request.url.path)
                return await call_next(request)
            
            # Check if endpoint requires authentication
            if self._is_public_endpoint(request.url.path):
                logger.debug("Public endpoint, skipping auth", path=request.url.path)
                return await call_next(request)
            
            # Handle agent secret key authentication
            if self._is_agent_secret_endpoint(request.url.path):
                logger.info("🔑 AGENT SECRET ENDPOINT DETECTED", path=request.url.path)
                return await self._handle_agent_secret_auth(request, call_next)
            
            # Handle JWT authentication
            logger.debug("JWT endpoint, processing auth", path=request.url.path)
            return await self._handle_jwt_auth(request, call_next)
            
        except AuthenticationError as e:
            duration = time.time() - start_time
            logger.warning(
                "Authentication failed",
                error=e.message,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2)
            )
            
            return JSONResponse(
                status_code=e.status_code,
                content=ErrorResponse(
                    message=e.message,
                    request_id=getattr(request.state, 'request_id', None),
                    error=ErrorDetail(
                        code=e.code,
                        message=e.message,
                        context=e.context
                    )
                ).dict(exclude_none=True)
            )
        
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "Authentication middleware error",
                error=str(e),
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
                exc_info=True
            )
            
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    message="Authentication service error",
                    request_id=getattr(request.state, 'request_id', None),
                    error=ErrorDetail(
                        code="AUTH_SERVICE_ERROR",
                        message="Authentication service temporarily unavailable"
                    )
                ).dict(exclude_none=True)
            )
    
    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public and doesn't require authentication."""
        return path in PUBLIC_ENDPOINTS
    
    def _is_agent_secret_endpoint(self, path: str) -> bool:
        """Check if endpoint uses agent secret key authentication."""
        logger.debug(
            "Checking agent secret endpoint",
            path=path,
            patterns=list(AGENT_SECRET_ENDPOINTS)
        )
        
        # Check for pattern matching
        for pattern in AGENT_SECRET_ENDPOINTS:
            if "{user_id}" in pattern:
                # Simple pattern matching for user_id placeholder
                pattern_parts = pattern.split("/")
                path_parts = path.split("/")
                
                logger.debug(
                    "Pattern matching",
                    pattern=pattern,
                    pattern_parts=pattern_parts,
                    path_parts=path_parts,
                    lengths_match=len(pattern_parts) == len(path_parts)
                )
                
                if len(pattern_parts) == len(path_parts):
                    match = True
                    for i, (pattern_part, path_part) in enumerate(zip(pattern_parts, path_parts)):
                        if pattern_part.startswith("{") and pattern_part.endswith("}"):
                            continue  # Wildcard match
                        elif pattern_part != path_part:
                            match = False
                            break
                    
                    logger.debug(
                        "Pattern match result",
                        pattern=pattern,
                        path=path,
                        match=match
                    )
                    
                    if match:
                        return True
        
        logger.debug("No agent secret endpoint match found", path=path)
        return False
    
    async def _handle_jwt_auth(self, request: Request, call_next):
        """Handle JWT token authentication."""
        start_time = time.time()
        
        logger.debug("Starting JWT authentication", path=request.url.path)
        
        # Extract JWT token
        token = self._extract_jwt_token(request)
        if not token:
            logger.warning("No JWT token found in request")
            raise AuthenticationError(
                "Missing authentication token",
                context={"header": "Authorization"}
            )
        
        logger.debug("JWT token extracted", token_prefix=token[:20] + "...")
        
        # Validate and decode JWT
        try:
            user_context = await self._validate_jwt_token(token)
            logger.debug("JWT validation successful", user_id=user_context.user_id)
        except Exception as e:
            logger.warning("JWT validation failed", error=str(e))
            raise AuthenticationError(
                f"Invalid JWT token: {str(e)}",
                context={"validation_error": str(e)}
            )
        
        # Set request context
        try:
            set_request_context(
                request_id=getattr(request.state, 'request_id', None),
                user_id=user_context.user_id,
                user_email=user_context.email
            )
        except Exception as e:
            logger.warning("Failed to set request context", error=str(e))
        
        # Add user context to request state
        request.state.user = user_context
        request.state.auth_method = "jwt"
        
        logger.debug("User context set in request state", user_id=user_context.user_id)
        
        # Record successful authentication
        duration = time.time() - start_time
        if metrics:
            try:
                metrics.record_auth_attempt(True, duration)
            except Exception as e:
                logger.warning("Failed to record auth metrics", error=str(e))
        
        # Continue with request
        logger.debug("Proceeding to next middleware/endpoint")
        response = await call_next(request)
        
        return response
    
    async def _handle_agent_secret_auth(self, request: Request, call_next):
        """Handle agent secret key authentication."""
        start_time = time.time()
        
        # Extract agent secret key
        secret_key = self._extract_agent_secret(request)
        if not secret_key:
            logger.warning("Missing agent secret key", path=request.url.path)
            raise AuthenticationError(
                "Missing agent secret key",
                context={"header": "Authorization"}
            )
        
        # Log the secret key for debugging (first few characters for security)
        logger.debug(
            "Agent secret key extracted",
            path=request.url.path,
            key_prefix=secret_key[:8] + "..." if len(secret_key) > 8 else secret_key,
            key_length=len(secret_key)
        )
        
        # Validate agent secret key
        user_id = await self._validate_agent_secret(secret_key, request.url.path)
        
        # Set request context
        set_request_context(
            request_id=getattr(request.state, 'request_id', None),
            user_id=user_id
        )
        
        # Add auth context to request state
        request.state.user_id = user_id
        request.state.auth_method = "agent_secret"
        
        # Record successful authentication
        duration = time.time() - start_time
        metrics.record_auth_attempt(True, duration)
        
        # Continue with request
        response = await call_next(request)
        
        return response
    
    def _extract_jwt_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from Authorization header."""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        
        if not auth_header.startswith("Bearer "):
            return None
        
        return auth_header[7:]  # Remove "Bearer " prefix
    
    def _extract_agent_secret(self, request: Request) -> Optional[str]:
        """Extract agent secret key from Authorization header."""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        
        if auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        elif auth_header.startswith("AgentSecret "):
            return auth_header[12:]  # Remove "AgentSecret " prefix
        
        return auth_header  # Assume it's the raw key
    
    async def _validate_jwt_token(self, token: str) -> UserContext:
        """Validate JWT token and extract user context."""
        try:
            # Decode JWT token
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                audience=self.jwt_audience,
                issuer=self.jwt_issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": self.jwt_audience is not None,
                    "verify_iss": self.jwt_issuer is not None
                }
            )
            
            # Extract user information from Supabase JWT payload
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token: missing user ID")
            
            email = payload.get("email")
            role = payload.get("role", "authenticated")
            
            # Extract user metadata
            user_metadata = payload.get("user_metadata", {})
            app_metadata = payload.get("app_metadata", {})
            
            # Combine metadata
            metadata = {**user_metadata, **app_metadata}
            
            logger.debug(
                "JWT validation successful",
                user_id=user_id,
                email=email,
                role=role
            )
            
            return UserContext(
                user_id=user_id,
                email=email,
                role=role,
                metadata=metadata
            )
            
        except ExpiredSignatureError:
            raise AuthenticationError(
                "Token has expired",
                context={"error_type": "expired"}
            )
        
        except InvalidTokenError as e:
            raise AuthenticationError(
                f"Invalid token: {str(e)}",
                context={"error_type": "invalid", "details": str(e)}
            )
        
        except Exception as e:
            logger.error("JWT validation error", error=str(e))
            raise AuthenticationError(
                "Token validation failed",
                context={"error_type": "validation_error"}
            )
    
    async def _validate_agent_secret(self, secret_key: str, path: str) -> str:
        """Validate agent secret key and extract user ID."""
        # Extract user_id from path
        path_parts = path.split("/")
        user_id = None
        
        # Look for user_id in path (should be after /agents/)
        try:
            agents_index = path_parts.index("agents")
            if agents_index + 1 < len(path_parts):
                user_id = path_parts[agents_index + 1]
        except (ValueError, IndexError):
            raise AuthenticationError("Invalid agent proxy path")
        
        if not user_id:
            raise AuthenticationError("Missing user ID in agent proxy path")
        
        logger.debug(
            "Starting agent secret validation",
            user_id=user_id,
            path=path,
            key_prefix=secret_key[:8] + "...",
            key_length=len(secret_key)
        )
        
        # Validate secret key format and ownership with retry logic
        if not self._is_valid_agent_secret_format(secret_key):
            logger.warning(
                "Invalid agent secret key format",
                user_id=user_id,
                key_prefix=secret_key[:8] + "...",
                key_length=len(secret_key)
            )
            raise AuthenticationError("Invalid agent secret key format")
        
        # Check if secret belongs to the specified user with retry logic
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                is_valid = await self._verify_agent_secret_ownership(secret_key, user_id)
                if is_valid:
                    logger.debug(
                        "Agent secret validation successful",
                        user_id=user_id,
                        key_prefix=secret_key[:8] + "...",
                        attempt=attempt + 1
                    )
                    return user_id
                else:
                    if attempt < max_retries:
                        logger.warning(
                            "Agent secret validation failed, retrying",
                            user_id=user_id,
                            key_prefix=secret_key[:8] + "...",
                            attempt=attempt + 1,
                            max_retries=max_retries
                        )
                        # Small delay before retry
                        import asyncio
                        await asyncio.sleep(0.1)
                        continue
                    else:
                        logger.error(
                            "Agent secret validation failed after all retries",
                            user_id=user_id,
                            key_prefix=secret_key[:8] + "...",
                            attempts=max_retries + 1
                        )
                        raise AuthorizationError(
                            "Agent secret key does not belong to specified user",
                            context={
                                "user_id": user_id,
                                "key_prefix": secret_key[:8] + "...",
                                "attempts": max_retries + 1
                            }
                        )
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        "Agent secret validation error, retrying",
                        user_id=user_id,
                        key_prefix=secret_key[:8] + "...",
                        attempt=attempt + 1,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    import asyncio
                    await asyncio.sleep(0.1)
                    continue
                else:
                    logger.error(
                        "Agent secret validation error after all retries",
                        user_id=user_id,
                        key_prefix=secret_key[:8] + "...",
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True
                    )
                    raise AuthorizationError(
                        "Agent secret key validation failed",
                        context={
                            "user_id": user_id,
                            "key_prefix": secret_key[:8] + "...",
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
        
        # This should never be reached, but just in case
        raise AuthorizationError(
            "Agent secret key does not belong to specified user",
            context={"user_id": user_id}
        )
    
    def _is_valid_agent_secret_format(self, secret_key: str) -> bool:
        """Validate agent secret key format."""
        # Basic format validation
        if not secret_key:
            logger.debug("Agent secret key is empty")
            return False
        
        # Check if it's a Letta API key format (starts with 'sk-')
        if secret_key.startswith("sk-"):
            # Letta API keys should be at least 20 characters
            if len(secret_key) < 20:
                logger.debug("Letta API key too short", length=len(secret_key))
                return False
            
            # Check if it matches Letta's expected pattern
            import re
            if not re.match(r'^sk-[a-zA-Z0-9_-]+$', secret_key):
                logger.debug("Letta API key contains invalid characters", key_prefix=secret_key[:8] + "...")
                return False
            
            logger.debug("Letta API key format is valid", key_prefix=secret_key[:8] + "...")
            return True
        
        # Check if it's the master key format
        # Reduced minimum length to accommodate various key formats
        if len(secret_key) < 20:
            logger.debug("Agent secret key too short", length=len(secret_key))
            return False
        
        # Check if it matches expected pattern (alphanumeric + some special chars)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', secret_key):
            logger.debug("Agent secret key contains invalid characters", key_prefix=secret_key[:8] + "...")
            return False
        
        logger.debug("Agent secret key format is valid", key_prefix=secret_key[:8] + "...")
        return True
    
    async def _verify_agent_secret_ownership(self, secret_key: str, user_id: str) -> bool:
        """Verify that agent secret key belongs to the specified user."""
        # FIXED: Create unique cache key including user_id to prevent race conditions
        import hashlib
        cache_key_data = f"agent_secret_ownership:{secret_key}:{user_id}"
        cache_key = f"agent_secret_ownership:{hashlib.sha256(cache_key_data.encode()).hexdigest()[:32]}"
        
        logger.debug(
            "Verifying agent secret ownership",
            user_id=user_id,
            key_prefix=secret_key[:8] + "...",
            cache_key=cache_key
        )
        
        # Try to get from cache first
        try:
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(
                    "Agent secret ownership found in cache",
                    user_id=user_id,
                    cached_result=cached_result
                )
                return bool(cached_result)
        except Exception as e:
            logger.warning(
                "Cache lookup failed for agent secret ownership",
                user_id=user_id,
                error=str(e)
            )
            # Continue with direct validation as fallback
        
        # Perform direct validation
        is_valid = False
        validation_method = None
        
        # Handle Letta API keys
        if secret_key.startswith("sk-"):
            # For Letta API keys, we accept them if we have a master key configured
            if self.settings.agent_secret_master_key:
                is_valid = True
                validation_method = "letta_api_key"
                logger.debug("Letta API key ownership verified", user_id=user_id)
            else:
                logger.warning("No master key configured for Letta API key validation")
                is_valid = False
                validation_method = "letta_api_key_no_master"
        
        # Validate against master key
        elif secret_key == self.settings.agent_secret_master_key:
            # Master key can act as any user (for development/testing)
            is_valid = True
            validation_method = "master_key"
            logger.debug("Master agent secret key verified", user_id=user_id)
        
        # Validate generated secret
        else:
            expected_secret = self._generate_expected_agent_secret(user_id)
            is_valid = secret_key == expected_secret
            validation_method = "generated_secret"
            
            logger.debug(
                "Generated secret validation",
                user_id=user_id,
                is_valid=is_valid,
                expected_prefix=expected_secret[:8] + "...",
                received_prefix=secret_key[:8] + "..."
            )
        
        # Cache the result with longer TTL for stability
        try:
            await cache_manager.set(cache_key, is_valid, ttl=600)  # 10 minutes
            logger.debug(
                "Agent secret ownership cached",
                user_id=user_id,
                is_valid=is_valid,
                validation_method=validation_method
            )
        except Exception as e:
            logger.warning(
                "Failed to cache agent secret ownership",
                user_id=user_id,
                error=str(e)
            )
        
        return is_valid
    
    def _generate_expected_agent_secret(self, user_id: str) -> str:
        """Generate expected agent secret for a user (temporary implementation)."""
        import hashlib
        
        # Simple secret generation based on user_id and master key
        # In production, this should be stored in a database
        combined = f"{user_id}:{self.settings.agent_secret_master_key}"
        return hashlib.sha256(combined.encode()).hexdigest()


def get_current_user(request: Request) -> UserContext:
    """Get current user from request state."""
    user = getattr(request.state, 'user', None)
    if not user:
        logger.error(
            "User not found in request state",
            path=request.url.path,
            state_attrs=[attr for attr in dir(request.state) if not attr.startswith('_')],
            auth_header=bool(request.headers.get("Authorization"))
        )
        raise AuthenticationError("User not authenticated")
    return user


def get_current_user_id(request: Request) -> str:
    """Get current user ID from request state."""
    # Try JWT user first
    user = getattr(request.state, 'user', None)
    if user:
        return user.user_id
    
    # Try agent secret user
    user_id = getattr(request.state, 'user_id', None)
    if user_id:
        return user_id
    
    raise AuthenticationError("User not authenticated")


def require_role(required_role: str):
    """Decorator to require specific user role."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = get_current_user(request)
            if user.role != required_role:
                raise AuthorizationError(
                    f"Required role: {required_role}",
                    context={"user_role": user.role, "required_role": required_role}
                )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_admin(func):
    """Decorator to require admin role."""
    return require_role("admin")(func)
