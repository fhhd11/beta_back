"""
Direct Supabase client for efficient user profile and LiteLLM key retrieval.
"""

import time
from typing import Optional, Dict, Any
import httpx
import structlog

from src.config.settings import get_settings
from src.utils.cache import cache_manager
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError

logger = structlog.get_logger(__name__)


class SupabaseClient:
    """Direct Supabase client with caching for user profiles."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.supabase_url).rstrip('/')
        self.timeout = self.settings.request_timeout
        
        # Configure HTTP client with Supabase service key
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.supabase_service_key}",
                "apikey": self.settings.supabase_service_key
            },
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100
            )
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def get_user_litellm_key(self, user_id: str) -> Optional[str]:
        """
        Get user's LiteLLM key directly from Supabase with caching.
        
        Args:
            user_id: User ID to look up
            
        Returns:
            LiteLLM key if found, None otherwise
        """
        cache_key = f"user_litellm_key:{user_id}"
        
        # Try cache first
        try:
            cached_key = await cache_manager.get(cache_key)
            if cached_key is not None:
                logger.debug(
                    "User LiteLLM key found in cache",
                    user_id=user_id,
                    key_prefix=cached_key[:8] + "..." if cached_key else "None"
                )
                metrics.record_cache_operation("get", "user_litellm_key", True)
                return cached_key
        except Exception as e:
            logger.warning(
                "Cache lookup failed for user LiteLLM key",
                user_id=user_id,
                error=str(e)
            )
        
        # Query Supabase directly
        start_time = time.time()
        
        try:
            # Query user profile table for LiteLLM key using direct table access
            response = await self.client.get(
                f"/rest/v1/user_profiles",
                params={
                    "id": f"eq.{user_id}",
                    "select": "id,email,name,litellm_key,letta_agent_id,agent_status,created_at,updated_at"
                }
            )
            
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_upstream_request("supabase", response.status_code, duration)
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle Supabase REST API response format (array of objects)
                litellm_key = None
                if isinstance(data, list) and len(data) > 0:
                    user_data = data[0]
                    litellm_key = user_data.get("litellm_key")
                elif isinstance(data, dict):
                    litellm_key = data.get("litellm_key")
                
                # Cache the result (even if None)
                try:
                    await cache_manager.set(cache_key, litellm_key, ttl=900)  # 15 minutes
                    logger.debug(
                        "User LiteLLM key cached",
                        user_id=user_id,
                        key_prefix=litellm_key[:8] + "..." if litellm_key else "None",
                        ttl=900
                    )
                except Exception as cache_error:
                    logger.warning(
                        "Failed to cache user LiteLLM key",
                        user_id=user_id,
                        error=str(cache_error)
                    )
                
                logger.debug(
                    "User LiteLLM key retrieved from Supabase",
                    user_id=user_id,
                    key_prefix=litellm_key[:8] + "..." if litellm_key else "None",
                    duration_ms=round(duration * 1000, 2)
                )
                
                return litellm_key
                
            elif response.status_code == 404:
                # User not found - cache None result
                await cache_manager.set(cache_key, None, ttl=300)  # 5 minutes for not found
                logger.warning(
                    "User not found in Supabase",
                    user_id=user_id,
                    status_code=response.status_code
                )
                return None
                
            else:
                # Other error
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                logger.error(
                    "Failed to get user LiteLLM key from Supabase",
                    user_id=user_id,
                    status_code=response.status_code,
                    error=error_detail,
                    duration_ms=round(duration * 1000, 2)
                )
                
                raise UpstreamError(
                    f"Supabase request failed: {response.status_code}",
                    service_name="supabase",
                    upstream_status=response.status_code,
                    context={"detail": error_detail, "user_id": user_id}
                )
                
        except httpx.TimeoutException:
            duration = time.time() - start_time
            metrics.record_upstream_request("supabase", 408, duration)
            
            logger.error(
                "Supabase request timeout",
                user_id=user_id,
                timeout=self.timeout,
                duration_ms=round(duration * 1000, 2)
            )
            
            raise RequestTimeoutError(
                "Supabase request timeout",
                timeout_seconds=self.timeout,
                context={"user_id": user_id}
            )
        
        except httpx.RequestError as e:
            duration = time.time() - start_time
            metrics.record_upstream_request("supabase", 502, duration)
            
            logger.error(
                "Supabase connection error",
                user_id=user_id,
                error=str(e),
                duration_ms=round(duration * 1000, 2)
            )
            
            raise UpstreamError(
                f"Supabase connection error: {str(e)}",
                service_name="supabase",
                context={"user_id": user_id, "error": str(e)}
            )
    
    async def get_user_profile_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get complete user profile data from Supabase with caching.
        
        Args:
            user_id: User ID to look up
            
        Returns:
            User profile data if found, None otherwise
        """
        cache_key = f"user_profile:{user_id}"
        
        # Try cache first
        try:
            cached_profile = await cache_manager.get(cache_key)
            if cached_profile is not None:
                logger.debug(
                    "User profile found in cache",
                    user_id=user_id
                )
                metrics.record_cache_operation("get", "user_profile", True)
                return cached_profile
        except Exception as e:
            logger.warning(
                "Cache lookup failed for user profile",
                user_id=user_id,
                error=str(e)
            )
        
        # Query Supabase directly
        start_time = time.time()
        
        try:
            # Query user profile table using direct table access
            response = await self.client.get(
                f"/rest/v1/user_profiles",
                params={
                    "id": f"eq.{user_id}",
                    "select": "*"
                }
            )
            
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_upstream_request("supabase", response.status_code, duration)
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle Supabase REST API response format (array of objects)
                profile_data = None
                if isinstance(data, list) and len(data) > 0:
                    profile_data = data[0]
                elif isinstance(data, dict):
                    profile_data = data
                
                # Cache the result (even if None)
                try:
                    await cache_manager.set(cache_key, profile_data, ttl=900)  # 15 minutes
                    logger.debug(
                        "User profile cached",
                        user_id=user_id,
                        ttl=900
                    )
                except Exception as cache_error:
                    logger.warning(
                        "Failed to cache user profile",
                        user_id=user_id,
                        error=str(cache_error)
                    )
                
                logger.debug(
                    "User profile retrieved from Supabase",
                    user_id=user_id,
                    duration_ms=round(duration * 1000, 2)
                )
                
                return profile_data
                
            elif response.status_code == 404:
                # User not found - cache None result
                await cache_manager.set(cache_key, None, ttl=300)  # 5 minutes for not found
                logger.warning(
                    "User profile not found in Supabase",
                    user_id=user_id,
                    status_code=response.status_code
                )
                return None
                
            else:
                # Other error
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                logger.error(
                    "Failed to get user profile from Supabase",
                    user_id=user_id,
                    status_code=response.status_code,
                    error=error_detail,
                    duration_ms=round(duration * 1000, 2)
                )
                
                raise UpstreamError(
                    f"Supabase request failed: {response.status_code}",
                    service_name="supabase",
                    upstream_status=response.status_code,
                    context={"detail": error_detail, "user_id": user_id}
                )
                
        except httpx.TimeoutException:
            duration = time.time() - start_time
            metrics.record_upstream_request("supabase", 408, duration)
            
            logger.error(
                "Supabase request timeout for user profile",
                user_id=user_id,
                timeout=self.timeout,
                duration_ms=round(duration * 1000, 2)
            )
            
            raise RequestTimeoutError(
                "Supabase request timeout",
                timeout_seconds=self.timeout,
                context={"user_id": user_id}
            )
        
        except httpx.RequestError as e:
            duration = time.time() - start_time
            metrics.record_upstream_request("supabase", 502, duration)
            
            logger.error(
                "Supabase connection error for user profile",
                user_id=user_id,
                error=str(e),
                duration_ms=round(duration * 1000, 2)
            )
            
            raise UpstreamError(
                f"Supabase connection error: {str(e)}",
                service_name="supabase",
                context={"user_id": user_id, "error": str(e)}
            )


# Global client instance
_supabase_client: Optional[SupabaseClient] = None


async def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client instance."""
    global _supabase_client
    
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    
    return _supabase_client


async def close_supabase_client():
    """Close Supabase client."""
    global _supabase_client
    
    if _supabase_client:
        await _supabase_client.close()
        _supabase_client = None
