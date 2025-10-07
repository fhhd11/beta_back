"""
LiteLLM client for key management and user operations.
"""

import time
from typing import Optional, Dict, Any
import httpx
import structlog

from src.config.settings import get_settings
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError

logger = structlog.get_logger(__name__)


class LiteLLMClient:
    """HTTP client for LiteLLM API operations."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.litellm_base_url).rstrip('/')
        self.timeout = self.settings.request_timeout
        
        # Prepare headers with master key if available
        headers = {
            "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
            "Content-Type": "application/json",
        }
        
        # Add LiteLLM master key for authentication
        if self.settings.litellm_master_key:
            headers["Authorization"] = f"Bearer {self.settings.litellm_master_key}"
            logger.info(
                "LiteLLM client initialized with master key",
                key_prefix=self.settings.litellm_master_key[:8] + "..." if len(self.settings.litellm_master_key) > 8 else "***"
            )
        else:
            logger.warning("LiteLLM client initialized WITHOUT master key - some operations may fail")
        
        # Configure HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers=headers,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100
            )
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def delete_key(self, litellm_key: str) -> bool:
        """
        Delete a LiteLLM API key.
        
        Args:
            litellm_key: The LiteLLM API key to delete
            
        Returns:
            True if deleted successfully, False if key not found
            
        Raises:
            UpstreamError: If deletion fails
        """
        if not litellm_key:
            logger.warning("Attempted to delete empty LiteLLM key")
            return False
        
        start_time = time.time()
        
        try:
            logger.info(
                "Deleting LiteLLM key",
                key_prefix=litellm_key[:8] + "..." if len(litellm_key) > 8 else "***"
            )
            
            # LiteLLM key deletion endpoint
            response = await self.client.post(
                "/key/delete",
                json={"keys": [litellm_key]}
            )
            
            duration = time.time() - start_time
            metrics.record_upstream_request("litellm", response.status_code, duration)
            
            if response.status_code == 200:
                logger.info(
                    "LiteLLM key deleted successfully",
                    key_prefix=litellm_key[:8] + "...",
                    duration_ms=round(duration * 1000, 2)
                )
                return True
            elif response.status_code == 404:
                logger.warning(
                    "LiteLLM key not found (already deleted?)",
                    key_prefix=litellm_key[:8] + "...",
                    duration_ms=round(duration * 1000, 2)
                )
                return False
            else:
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                logger.error(
                    "Failed to delete LiteLLM key",
                    status_code=response.status_code,
                    error=error_detail,
                    duration_ms=round(duration * 1000, 2)
                )
                
                raise UpstreamError(
                    f"LiteLLM key deletion failed: {response.status_code}",
                    service_name="litellm",
                    upstream_status=response.status_code,
                    context={"detail": error_detail}
                )
        
        except httpx.TimeoutException:
            duration = time.time() - start_time
            metrics.record_upstream_request("litellm", 408, duration)
            
            logger.error(
                "LiteLLM request timeout",
                timeout=self.timeout,
                duration_ms=round(duration * 1000, 2)
            )
            
            raise RequestTimeoutError(
                "LiteLLM request timeout",
                timeout_seconds=self.timeout
            )
        
        except httpx.RequestError as e:
            duration = time.time() - start_time
            metrics.record_upstream_request("litellm", 502, duration)
            
            logger.error(
                "LiteLLM connection error",
                error=str(e),
                duration_ms=round(duration * 1000, 2)
            )
            
            raise UpstreamError(
                f"LiteLLM connection error: {str(e)}",
                service_name="litellm",
                context={"error": str(e)}
            )
    
    async def get_key_info(self, litellm_key: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a LiteLLM key.
        
        Args:
            litellm_key: The LiteLLM API key
            
        Returns:
            Key information if found, None otherwise
        """
        try:
            response = await self.client.get(
                "/key/info",
                params={"key": litellm_key}
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(
                    "Failed to get LiteLLM key info",
                    status_code=response.status_code
                )
                return None
                
        except Exception as e:
            logger.warning("LiteLLM key info request failed", error=str(e))
            return None


# Global client instance
_litellm_client: Optional[LiteLLMClient] = None


async def get_litellm_client() -> LiteLLMClient:
    """Get or create LiteLLM client instance."""
    global _litellm_client
    
    if _litellm_client is None:
        _litellm_client = LiteLLMClient()
    
    return _litellm_client


async def close_litellm_client():
    """Close LiteLLM client."""
    global _litellm_client
    
    if _litellm_client:
        await _litellm_client.close()
        _litellm_client = None

