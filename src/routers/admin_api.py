"""
Admin API endpoints for user management.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
import structlog

from src.dependencies.admin_auth import verify_admin_auth
from src.services.admin_service import get_admin_service

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/users",
    response_model=List[Dict[str, Any]],
    summary="Get All Users",
    description="Get list of all users (admin only)"
)
async def get_all_users(
    admin_username: str = Depends(verify_admin_auth)
):
    """Get all users from the system."""
    logger.info("Admin fetching all users", admin=admin_username)
    
    admin_service = get_admin_service()
    users = await admin_service.get_all_users()
    
    return users


@router.get(
    "/users/search",
    response_model=List[Dict[str, Any]],
    summary="Search Users",
    description="Search users by email (admin only)"
)
async def search_users(
    q: str = Query(..., description="Search query (email)"),
    admin_username: str = Depends(verify_admin_auth)
):
    """Search users by email."""
    logger.info("Admin searching users", admin=admin_username, query=q)
    
    admin_service = get_admin_service()
    users = await admin_service.search_users(q)
    
    return users


@router.delete(
    "/users/{user_id}",
    response_model=Dict[str, Any],
    summary="Delete User",
    description="Delete a user and all associated data (admin only)"
)
async def delete_user(
    user_id: str,
    admin_username: str = Depends(verify_admin_auth)
):
    """Delete a user with cascade deletion of all associated data."""
    logger.warning(
        "Admin deleting user",
        admin=admin_username,
        user_id=user_id
    )
    
    admin_service = get_admin_service()
    
    try:
        result = await admin_service.delete_user_cascade(user_id)
        
        logger.info(
            "User deleted successfully by admin",
            admin=admin_username,
            user_id=user_id,
            result=result
        )
        
        return {
            "status": "success",
            "message": f"User {user_id} deleted successfully",
            "result": result
        }
        
    except ValueError as e:
        logger.warning("User not found for deletion", user_id=user_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to delete user",
            admin=admin_username,
            user_id=user_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@router.post(
    "/users/delete-all",
    response_model=Dict[str, Any],
    summary="Delete All Users",
    description="Delete all users from the system (admin only, DANGEROUS)"
)
async def delete_all_users(
    admin_username: str = Depends(verify_admin_auth)
):
    """
    Delete all users from the system.
    This is a DANGEROUS operation that cannot be undone.
    """
    logger.warning(
        "Admin initiating DELETE ALL USERS operation",
        admin=admin_username
    )
    
    admin_service = get_admin_service()
    
    try:
        result = await admin_service.delete_all_users()
        
        if result["status"] == "success":
            logger.warning(
                "All users deleted successfully by admin",
                admin=admin_username,
                deleted_count=result["deleted"]
            )
        else:
            logger.error(
                "Delete all users failed",
                admin=admin_username,
                result=result
            )
        
        return result
        
    except Exception as e:
        logger.error(
            "Failed to delete all users",
            admin=admin_username,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete all users: {str(e)}")

