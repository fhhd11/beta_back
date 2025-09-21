"""
Debug endpoints for testing authentication.
"""

from fastapi import APIRouter, Request
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/debug/auth")
async def debug_auth(request: Request):
    """Debug authentication state."""
    
    # Check request state
    auth_method = getattr(request.state, 'auth_method', None)
    user = getattr(request.state, 'user', None)
    user_id = getattr(request.state, 'user_id', None)
    
    # Check headers
    auth_header = request.headers.get("Authorization", "Not provided")
    
    debug_info = {
        "request_state": {
            "auth_method": auth_method,
            "user": str(user) if user else None,
            "user_id": user_id
        },
        "headers": {
            "authorization": auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
        },
        "middleware_status": "Auth middleware should have processed this request"
    }
    
    logger.info("Debug auth endpoint called", debug_info=debug_info)
    
    return debug_info
