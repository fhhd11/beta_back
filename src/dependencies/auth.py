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
