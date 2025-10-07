"""
Admin authentication dependency using HTTP Basic Auth.
"""

import secrets
from fastapi import Request, HTTPException, status
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


async def verify_admin_auth(request: Request) -> str:
    """
    Verify admin authentication using HTTP Basic Auth.
    
    Checks the Authorization header for Basic Auth credentials.
    Expected: username can be anything, password must match ADMIN_SECRET_KEY.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Admin username if authenticated
        
    Raises:
        HTTPException: If authentication fails
    """
    settings = get_settings()
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        logger.warning("Admin access attempt without Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic realm=\"Admin Panel\""}
        )
    
    # Parse Basic Auth
    if not auth_header.startswith("Basic "):
        logger.warning("Admin access attempt with non-Basic auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Basic authentication required",
            headers={"WWW-Authenticate": "Basic realm=\"Admin Panel\""}
        )
    
    try:
        # Decode Base64 credentials
        import base64
        
        encoded_credentials = auth_header[6:]  # Remove "Basic "
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        
        # Verify password against admin secret key
        # Use constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(password, settings.admin_secret_key):
            logger.warning(
                "Admin authentication failed - invalid key",
                username=username,
                key_prefix=password[:4] + "..." if len(password) > 4 else "***"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic realm=\"Admin Panel\""}
            )
        
        logger.info("Admin authenticated successfully", username=username)
        return username
        
    except ValueError as e:
        logger.warning("Admin authentication failed - malformed credentials", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed credentials",
            headers={"WWW-Authenticate": "Basic realm=\"Admin Panel\""}
        )
    except Exception as e:
        logger.error("Admin authentication error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Basic realm=\"Admin Panel\""}
        )

