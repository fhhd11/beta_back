"""
User management endpoints.
"""

from fastapi import APIRouter, Request, Depends
import structlog

from src.models.responses import UserProfile
from src.models.common import UserContext
from src.dependencies.auth import get_current_user, get_current_user_id
from src.services.ams_client import get_ams_client
from src.utils.cache import cached_user_profile

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get User Profile",
    description="Get current user's profile information including associated agents"
)
async def get_user_profile(
    request: Request,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Get user profile with cached response.
    
    Returns:
        UserProfile: Complete user profile with agents list
    """
    user_id = current_user.user_id
    logger.info("Getting user profile", user_id=user_id, email=current_user.email)
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Fetch user profile from AMS (with caching)
    user_profile = await ams_client.get_user_profile(user_id)
    
    logger.info(
        "User profile retrieved",
        user_id=user_id,
        agents_count=len(user_profile.agents)
    )
    
    return user_profile
