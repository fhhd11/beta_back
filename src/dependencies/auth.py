"""
Authentication dependencies for FastAPI endpoints.
"""

from fastapi import Request, HTTPException, status
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError
import structlog

from src.config.settings import get_settings
from src.models.common import UserContext

logger = structlog.get_logger(__name__)


async def get_current_user(request: Request) -> UserContext:
    """
    Dependency to get current authenticated user.
    This performs JWT validation directly as a dependency.
    """
    settings = get_settings()
    
    # Extract JWT token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # Remove "Bearer "
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": settings.jwt_audience is not None,
                "verify_iss": settings.jwt_issuer is not None
            }
        )
        
        # Extract user information
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        email = payload.get("email")
        role = payload.get("role", "authenticated")
        
        # Extract user metadata
        user_metadata = payload.get("user_metadata", {})
        app_metadata = payload.get("app_metadata", {})
        metadata = {**user_metadata, **app_metadata}
        
        user_context = UserContext(
            user_id=user_id,
            email=email,
            role=role,
            metadata=metadata
        )
        
        logger.debug(
            "JWT authentication successful",
            user_id=user_id,
            email=email,
            role=role
        )
        
        return user_context
        
    except ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    
    except JWTError as e:
        logger.warning("JWT validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    
    except Exception as e:
        logger.error("JWT validation error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed"
        )


async def get_current_user_id(request: Request) -> str:
    """Dependency to get current user ID."""
    user = await get_current_user(request)
    return user.user_id


async def verify_agent_secret_key(request: Request) -> str:
    """
    Dependency to verify Agent Secret Key authentication.
    Used for internal agent-to-service communication.
    
    This accepts both:
    1. The master agent secret key directly
    2. Letta's API key format (which should be validated against the master key)
    3. Generated agent secrets for specific users
    """
    settings = get_settings()
    
    # Extract API key from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid authorization header for agent secret key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    api_key = auth_header[7:]  # Remove "Bearer " prefix
    
    # Log the keys for debugging (only first few characters for security)
    logger.debug(
        "Agent secret key verification",
        received_key_prefix=api_key[:8] + "...",
        expected_key_prefix=settings.agent_secret_master_key[:8] + "..." if settings.agent_secret_master_key else "None",
        keys_match=api_key == settings.agent_secret_master_key,
        key_length=len(api_key)
    )
    
    # Basic format validation first
    if not api_key:
        logger.warning("Empty agent secret key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty agent secret key"
        )
    
    # Check if it's the master key directly
    if api_key == settings.agent_secret_master_key:
        logger.debug("Master agent secret key verified successfully")
        return api_key
    
    # Check if it's a Letta API key format (starts with 'sk-')
    if api_key.startswith("sk-") and len(api_key) >= 20:
        # Validate Letta key format more strictly
        import re
        if not re.match(r'^sk-[a-zA-Z0-9_-]+$', api_key):
            logger.warning(
                "Invalid Letta API key format", 
                key_prefix=api_key[:8] + "...",
                key_length=len(api_key)
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Letta API key format"
            )
        
        # For Letta API keys, we need to validate that they're authorized
        if settings.agent_secret_master_key:
            logger.debug("Letta API key format accepted", key_prefix=api_key[:8] + "...")
            return api_key
        else:
            logger.warning("No master key configured for Letta API key validation")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Agent secret key validation not configured"
            )
    
    # Check if it's a generated agent secret (hex format, length check)
    if len(api_key) == 64 and all(c in '0123456789abcdef' for c in api_key.lower()):
        # This looks like a generated secret, accept it (middleware will validate ownership)
        logger.debug("Generated agent secret format detected", key_prefix=api_key[:8] + "...")
        return api_key
    
    # Invalid key format
    logger.warning(
        "Invalid agent secret key format", 
        key_prefix=api_key[:8] + "...",
        key_length=len(api_key),
        starts_with_sk=api_key.startswith("sk-"),
        is_hex=len(api_key) == 64 and all(c in '0123456789abcdef' for c in api_key.lower())
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid agent secret key format"
    )