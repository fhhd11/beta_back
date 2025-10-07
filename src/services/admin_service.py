"""
Admin service for user management and cascade deletion.
"""

from typing import List, Dict, Any, Optional
import structlog

from src.services.supabase_client import get_supabase_client
from src.services.litellm_client import get_litellm_client
from src.routers.letta import get_letta_client
from src.utils.cache import cache_manager

logger = structlog.get_logger(__name__)


class AdminService:
    """Service for admin operations on users."""
    
    async def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all users from user_profiles table.
        
        Returns:
            List of user profile dictionaries
        """
        logger.info("Fetching all users for admin panel")
        
        supabase_client = await get_supabase_client()
        
        try:
            response = await supabase_client.client.get(
                "/rest/v1/user_profiles",
                params={
                    "select": "id,email,name,litellm_key,letta_agent_id,agent_status,created_at,updated_at",
                    "order": "created_at.desc"
                }
            )
            
            if response.status_code == 200:
                users = response.json()
                logger.info(f"Fetched {len(users)} users")
                return users if isinstance(users, list) else []
            else:
                logger.error(
                    "Failed to fetch users",
                    status_code=response.status_code,
                    error=response.text
                )
                return []
                
        except Exception as e:
            logger.error("Error fetching users", error=str(e))
            return []
    
    async def search_users(self, query: str) -> List[Dict[str, Any]]:
        """
        Search users by email.
        
        Args:
            query: Search query (email)
            
        Returns:
            List of matching user profile dictionaries
        """
        logger.info("Searching users", query=query)
        
        supabase_client = await get_supabase_client()
        
        try:
            # Use ilike for case-insensitive search
            response = await supabase_client.client.get(
                "/rest/v1/user_profiles",
                params={
                    "select": "id,email,name,litellm_key,letta_agent_id,agent_status,created_at,updated_at",
                    "email": f"ilike.%{query}%",
                    "order": "created_at.desc"
                }
            )
            
            if response.status_code == 200:
                users = response.json()
                logger.info(f"Found {len(users)} users matching query")
                return users if isinstance(users, list) else []
            else:
                logger.error(
                    "Failed to search users",
                    status_code=response.status_code,
                    error=response.text
                )
                return []
                
        except Exception as e:
            logger.error("Error searching users", error=str(e))
            return []
    
    async def delete_user_cascade(self, user_id: str) -> Dict[str, Any]:
        """
        Delete user and all associated data in cascade.
        
        Steps:
        1. Get user data from user_profiles
        2. Delete Letta agent
        3. Delete LiteLLM key
        4. Delete from user_profiles
        5. Delete from Supabase Auth
        6. Clear caches
        
        Args:
            user_id: User ID to delete
            
        Returns:
            Dictionary with deletion results
            
        Raises:
            Exception: If any step fails
        """
        logger.info("Starting cascade user deletion", user_id=user_id)
        
        supabase_client = await get_supabase_client()
        
        # Step 1: Get user data
        user_data = await supabase_client.get_user_profile_data(user_id)
        
        if not user_data:
            raise ValueError(f"User {user_id} not found in user_profiles")
        
        letta_agent_id = user_data.get("letta_agent_id")
        litellm_key = user_data.get("litellm_key")
        email = user_data.get("email", "unknown")
        
        logger.info(
            "User data retrieved for deletion",
            user_id=user_id,
            email=email,
            has_letta_agent=bool(letta_agent_id),
            has_litellm_key=bool(litellm_key)
        )
        
        result = {
            "user_id": user_id,
            "email": email,
            "letta_agent_deleted": False,
            "litellm_key_deleted": False,
            "profile_deleted": False,
            "auth_deleted": False
        }
        
        # Step 2: Delete Letta agent
        if letta_agent_id:
            try:
                logger.info("Deleting Letta agent", agent_id=letta_agent_id)
                letta_client = await get_letta_client()
                
                response = await letta_client.delete(f"/v1/agents/{letta_agent_id}")
                
                if response.status_code in [200, 204]:
                    logger.info("Letta agent deleted successfully", agent_id=letta_agent_id)
                    result["letta_agent_deleted"] = True
                elif response.status_code == 404:
                    logger.warning("Letta agent not found (already deleted?)", agent_id=letta_agent_id)
                    result["letta_agent_deleted"] = True  # Consider as success
                else:
                    raise Exception(f"Letta delete failed with status {response.status_code}: {response.text}")
                    
            except Exception as e:
                # If 404, it's ok (already deleted)
                if "404" in str(e):
                    logger.warning("Letta agent already deleted", agent_id=letta_agent_id)
                    result["letta_agent_deleted"] = True
                else:
                    logger.error("Failed to delete Letta agent", agent_id=letta_agent_id, error=str(e))
                    raise Exception(f"Failed to delete Letta agent {letta_agent_id}: {e}")
        
        # Step 3: Delete LiteLLM key
        if litellm_key:
            try:
                logger.info("Deleting LiteLLM key", key_prefix=litellm_key[:8] + "...")
                litellm_client = await get_litellm_client()
                
                deleted = await litellm_client.delete_key(litellm_key)
                result["litellm_key_deleted"] = True
                
                logger.info("LiteLLM key deletion completed", deleted=deleted)
                
            except Exception as e:
                # If 404, it's ok (already deleted)
                if "404" in str(e):
                    logger.warning("LiteLLM key already deleted")
                    result["litellm_key_deleted"] = True
                else:
                    logger.error("Failed to delete LiteLLM key", error=str(e))
                    raise Exception(f"Failed to delete LiteLLM key: {e}")
        
        # Step 4: Delete from user_profiles
        try:
            logger.info("Deleting from user_profiles", user_id=user_id)
            
            response = await supabase_client.client.delete(
                "/rest/v1/user_profiles",
                params={"id": f"eq.{user_id}"}
            )
            
            if response.status_code in [200, 204]:
                logger.info("User profile deleted successfully", user_id=user_id)
                result["profile_deleted"] = True
            else:
                raise Exception(f"Failed to delete from user_profiles: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error("Failed to delete user profile", user_id=user_id, error=str(e))
            raise Exception(f"Failed to delete user profile: {e}")
        
        # Step 5: Delete from Supabase Auth
        try:
            logger.info("Deleting from Supabase Auth", user_id=user_id)
            
            # Supabase Admin API endpoint for user deletion
            response = await supabase_client.client.delete(
                f"/auth/v1/admin/users/{user_id}"
            )
            
            if response.status_code in [200, 204]:
                logger.info("User deleted from Supabase Auth successfully", user_id=user_id)
                result["auth_deleted"] = True
            elif response.status_code == 404:
                logger.warning("User not found in Supabase Auth (already deleted?)", user_id=user_id)
                result["auth_deleted"] = True  # Consider as success
            else:
                raise Exception(f"Failed to delete from Supabase Auth: {response.status_code} - {response.text}")
                
        except Exception as e:
            # If 404, it's ok (already deleted)
            if "404" in str(e):
                logger.warning("User already deleted from Supabase Auth", user_id=user_id)
                result["auth_deleted"] = True
            else:
                logger.error("Failed to delete from Supabase Auth", user_id=user_id, error=str(e))
                raise Exception(f"Failed to delete from Supabase Auth: {e}")
        
        # Step 6: Clear caches
        try:
            logger.info("Clearing user caches", user_id=user_id)
            
            await cache_manager.delete(f"user_profile:{user_id}")
            await cache_manager.delete(f"user_litellm_key:{user_id}")
            await cache_manager.delete(f"ams_user_profile:{user_id}")
            
            logger.info("User caches cleared", user_id=user_id)
            
        except Exception as e:
            # Cache clearing failure is not critical
            logger.warning("Failed to clear user caches", user_id=user_id, error=str(e))
        
        logger.info(
            "User cascade deletion completed",
            user_id=user_id,
            email=email,
            result=result
        )
        
        return result
    
    async def delete_all_users(self) -> Dict[str, Any]:
        """
        Delete all users one by one.
        Stops at first error.
        
        Returns:
            Dictionary with deletion statistics and results
        """
        logger.warning("Starting deletion of ALL users - this is a destructive operation!")
        
        users = await self.get_all_users()
        total = len(users)
        
        if total == 0:
            return {
                "status": "success",
                "total": 0,
                "deleted": 0,
                "message": "No users to delete"
            }
        
        deleted = 0
        results = []
        
        for user in users:
            user_id = user.get("id")
            email = user.get("email", "unknown")
            
            try:
                logger.info(f"Deleting user {deleted + 1}/{total}", user_id=user_id, email=email)
                
                delete_result = await self.delete_user_cascade(user_id)
                deleted += 1
                
                results.append({
                    "user_id": user_id,
                    "email": email,
                    "status": "success",
                    "result": delete_result
                })
                
                logger.info(f"User {deleted}/{total} deleted successfully", user_id=user_id, email=email)
                
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Failed to delete user {deleted + 1}/{total}",
                    user_id=user_id,
                    email=email,
                    error=error_msg
                )
                
                return {
                    "status": "error",
                    "total": total,
                    "deleted": deleted,
                    "failed_at": deleted + 1,
                    "failed_user_id": user_id,
                    "failed_user_email": email,
                    "error": error_msg,
                    "results": results
                }
        
        return {
            "status": "success",
            "total": total,
            "deleted": deleted,
            "message": f"Successfully deleted all {deleted} users",
            "results": results
        }


# Global service instance
_admin_service: Optional[AdminService] = None


def get_admin_service() -> AdminService:
    """Get or create admin service instance."""
    global _admin_service
    
    if _admin_service is None:
        _admin_service = AdminService()
    
    return _admin_service

