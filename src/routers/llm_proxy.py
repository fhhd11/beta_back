"""
Internal agent-to-LLM proxy with Agent Secret Key authentication.
"""

import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends
import httpx
import structlog

from src.config.settings import get_settings
from src.dependencies.auth import get_current_user_id, verify_agent_secret_key
from src.models.requests import LLMProxyRequest
from src.models.responses import LLMResponse
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError, AuthorizationError
from src.middleware.circuit_breaker import circuit_breaker, CircuitBreakerConfig

logger = structlog.get_logger(__name__)

router = APIRouter()


class LLMProxyClient:
    """HTTP client for LiteLLM proxy with billing context."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.litellm_base_url).rstrip('/')
        self.timeout = self.settings.request_timeout
        
        # Configure HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                "Content-Type": "application/json"
            },
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100
            )
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def make_llm_request(
        self,
        request_data: LLMProxyRequest,
        user_id: str
    ) -> Dict[str, Any]:
        """Make LLM request with user billing context."""
        start_time = time.time()
        
        # Add user context for billing
        enhanced_request = request_data.dict(exclude_none=True)
        enhanced_request["user"] = user_id  # For billing attribution
        
        # Add metadata
        if "metadata" not in enhanced_request:
            enhanced_request["metadata"] = {}
        enhanced_request["metadata"].update({
            "gateway_version": self.settings.version,
            "user_id": user_id,
            "request_timestamp": time.time()
        })
        
        try:
            response = await self.client.post(
                "/chat/completions",
                json=enhanced_request
            )
            
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_upstream_request("litellm", response.status_code, duration)
            
            # Log request
            logger.debug(
                "LLM proxy request completed",
                user_id=user_id,
                model=request_data.model,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
            
            if response.status_code >= 400:
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                raise UpstreamError(
                    f"LLM proxy request failed: {response.status_code}",
                    service_name="litellm",
                    upstream_status=response.status_code,
                    context={"detail": error_detail}
                )
            
            # Parse response
            response_data = response.json()
            
            # Record LLM-specific metrics
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            metrics.record_llm_request(
                model=request_data.model,
                user_id=user_id,
                status="success",
                duration=duration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )
            
            return response_data
            
        except httpx.TimeoutException:
            duration = time.time() - start_time
            metrics.record_upstream_request("litellm", 408, duration)
            metrics.record_llm_request(
                model=request_data.model,
                user_id=user_id,
                status="timeout",
                duration=duration
            )
            
            raise RequestTimeoutError(
                "LLM proxy request timeout",
                timeout_seconds=self.timeout,
                context={"model": request_data.model, "user_id": user_id}
            )
        
        except httpx.RequestError as e:
            duration = time.time() - start_time
            metrics.record_upstream_request("litellm", 502, duration)
            metrics.record_llm_request(
                model=request_data.model,
                user_id=user_id,
                status="error",
                duration=duration
            )
            
            raise UpstreamError(
                f"LLM proxy connection error: {str(e)}",
                service_name="litellm",
                context={"model": request_data.model, "user_id": user_id, "error": str(e)}
            )


# Apply circuit breaker to the client
@circuit_breaker(
    service_name="litellm",
    config=CircuitBreakerConfig(
        service_name="litellm",
        failure_threshold=5,
        recovery_timeout=60
    )
)
class ResilientLLMProxyClient(LLMProxyClient):
    """LLM proxy client with circuit breaker protection."""
    pass


# Global client instance
_llm_proxy_client: Optional[LLMProxyClient] = None


async def get_llm_proxy_client() -> LLMProxyClient:
    """Get or create LLM proxy client instance."""
    global _llm_proxy_client
    
    if _llm_proxy_client is None:
        _llm_proxy_client = ResilientLLMProxyClient()
    
    return _llm_proxy_client


async def close_llm_proxy_client():
    """Close LLM proxy client."""
    global _llm_proxy_client
    
    if _llm_proxy_client:
        await _llm_proxy_client.close()
        _llm_proxy_client = None


@router.post(
    "/{user_id}/proxy",
    response_model=LLMResponse,
    summary="Agent-to-LLM Proxy",
    description="Internal proxy for agent-to-LLM requests with Agent Secret Key authentication"
)
async def agent_llm_proxy(
    user_id: str,
    request: Request,
    llm_request: LLMProxyRequest,
    authenticated_user_id: str = Depends(get_current_user_id)
):
    """
    Internal proxy for agent-to-LLM requests.
    
    Features:
    - Agent Secret Key authentication (different from JWT)
    - User billing context attribution
    - Rate limiting per user + model combination
    - Usage logging for billing
    - Circuit breaker protection
    
    Note: This endpoint uses Agent Secret Key authentication, not JWT.
    The user_id in the path must match the authenticated agent's owner.
    """
    # Verify that the authenticated user (via agent secret) matches the path user_id
    if authenticated_user_id != user_id:
        raise AuthorizationError(
            "Agent secret key does not match specified user ID",
            context={
                "path_user_id": user_id,
                "authenticated_user_id": authenticated_user_id
            }
        )
    
    logger.info(
        "Agent LLM proxy request",
        user_id=user_id,
        model=llm_request.model,
        messages_count=len(llm_request.messages),
        stream=llm_request.stream
    )
    
    # Get LLM proxy client
    llm_client = await get_llm_proxy_client()
    
    # Make LLM request
    response_data = await llm_client.make_llm_request(llm_request, user_id)
    
    # Log usage for billing
    usage = response_data.get("usage", {})
    logger.info(
        "LLM request completed",
        user_id=user_id,
        model=llm_request.model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0)
    )
    
    return LLMResponse(**response_data)


@router.post(
    "/{user_id}/proxy/chat/completions",
    summary="Letta Agent LLM Proxy",
    description="Internal proxy for Letta agent-to-LLM requests with Agent Secret Key authentication"
)
async def letta_agent_llm_proxy(
    user_id: str,
    request: Request,
    llm_request: LLMProxyRequest,
    api_key: str = Depends(verify_agent_secret_key)
):
    """
    Internal proxy for Letta agent-to-LLM requests.
    
    This endpoint is specifically designed for Letta agents to make LLM requests.
    It uses Agent Secret Key authentication instead of JWT.
    
    Features:
    - Agent Secret Key authentication (for Letta agents)
    - User billing context attribution
    - Rate limiting per user + model combination
    - Usage logging for billing
    - Circuit breaker protection
    """
    logger.info(
        "Letta agent LLM proxy request",
        user_id=user_id,
        model=llm_request.model,
        messages_count=len(llm_request.messages),
        stream=llm_request.stream,
        api_key_prefix=api_key[:8] + "..."
    )
    
    # Get LLM proxy client
    llm_client = await get_llm_proxy_client()
    
    # Make LLM request
    response_data = await llm_client.make_llm_request(llm_request, user_id)
    
    # Log usage for billing
    usage = response_data.get("usage", {})
    logger.info(
        "Letta LLM request completed",
        user_id=user_id,
        model=llm_request.model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0)
    )
    
    return LLMResponse(**response_data)
