"""
Internal agent-to-LLM proxy with Agent Secret Key authentication.
"""

import time
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import structlog

from src.config.settings import get_settings
from src.dependencies.auth import get_current_user_id, verify_agent_secret_key
from src.models.requests import LLMProxyRequest
from src.models.responses import LLMResponse
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError, AuthorizationError

logger = structlog.get_logger(__name__)

router = APIRouter()


class LLMProxyClient:
    """HTTP client for LiteLLM proxy with billing context."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.litellm_base_url).rstrip('/')
        self.timeout = self.settings.request_timeout
        
        # Configure HTTP client with optimized connection pooling
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=self.settings.http_connect_timeout,
                read=self.settings.http_read_timeout,
                write=self.settings.http_write_timeout,
                pool=self.settings.http_pool_timeout
            ),
            headers={
                "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                "Content-Type": "application/json",
                "Connection": "keep-alive"
            },
            limits=httpx.Limits(
                max_keepalive_connections=self.settings.http_max_keepalive_connections,
                max_connections=self.settings.http_max_connections,
                keepalive_expiry=self.settings.http_keepalive_expiry
            ),
            # CRITICAL: Disable automatic decompression and buffering
            follow_redirects=True,
            verify=True
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


class ResilientLLMProxyClient(LLMProxyClient):
    """LLM proxy client with circuit breaker protection.
    
    Note: Circuit breaker protection is handled by CircuitBreakerMiddleware
    in the main application middleware stack, not at the class level.
    """
    pass


# Global client instance
_llm_proxy_client: Optional[LLMProxyClient] = None


def get_llm_proxy_client() -> LLMProxyClient:
    """Get or create LLM proxy client instance.
    
    Note: This function is synchronous and should NOT be awaited.
    """
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
    summary="Agent-to-LLM Proxy",
    description="Internal proxy for agent-to-LLM requests with Agent Secret Key authentication"
)
@router.post(
    "/{user_id}/proxy/chat/completions",
    summary="Agent-to-LLM Proxy (Chat Completions)",
    description="Internal proxy for agent-to-LLM chat completion requests with Agent Secret Key authentication"
)
async def agent_llm_proxy(
    user_id: str,
    request: Request,
    api_key: str = Depends(verify_agent_secret_key)
):
    """
    Internal proxy for agent-to-LLM requests.
    
    Features:
    - Agent Secret Key authentication (different from JWT)
    - Direct passthrough to LLM service without validation
    - User billing context attribution
    
    Note: This endpoint uses Agent Secret Key authentication, not JWT.
    We pass requests directly to the LLM service and return responses as-is.
    """
    logger.info(
        "LLM proxy request started",
        user_id=user_id,
        request_path=str(request.url.path),
        request_method=request.method,
        api_key_prefix=api_key[:8] + "..." if api_key else "None"
    )
    
    # Get raw request body
    try:
        request_body = await request.json()
    except Exception as e:
        logger.error(
            "Failed to parse request body",
            user_id=user_id,
            error=str(e)
        )
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON in request body", "detail": str(e)}
        )
    
    # Extract basic info for logging
    model = request_body.get("model", "unknown")
    messages = request_body.get("messages", [])
    stream = request_body.get("stream", False)
    
    logger.info(
        "=== LLM PROXY REQUEST START ===",
        user_id=user_id,
        model=model,
        messages_count=len(messages),
        stream=stream,
        request_body_keys=list(request_body.keys()) if request_body else []
    )
    
    # Get settings for configuration
    settings = get_settings()
    
    # Get LLM proxy client
    try:
        logger.debug("About to call get_llm_proxy_client()", user_id=user_id)
        llm_client = get_llm_proxy_client()
        logger.debug(
            "LLM client initialized successfully",
            user_id=user_id,
            base_url=llm_client.base_url,
            client_type=type(llm_client).__name__
        )
    except Exception as e:
        logger.error(
            "Failed to get LLM proxy client",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to initialize LLM client", "detail": str(e)}
        )
    
    # Get user's LiteLLM API key directly from Supabase (optimized with caching)
    try:
        from src.services.supabase_client import get_supabase_client
        supabase_client = await get_supabase_client()
        litellm_key = await supabase_client.get_user_litellm_key(user_id)
        
        if not litellm_key:
            logger.warning(
                "User LiteLLM key not found",
                user_id=user_id
            )
            return JSONResponse(
                status_code=400,
                content={"error": "User LiteLLM key not found", "detail": "User does not have a LiteLLM API key configured"}
            )
        
        logger.debug(
            "User LiteLLM key retrieved",
            user_id=user_id,
            key_prefix=litellm_key[:8] + "..."
        )
        
        # Cache successful validation for faster subsequent requests
        validation_cache_key = f"proxy_validation:{user_id}"
        try:
            from src.utils.cache import cache_manager
            await cache_manager.set(validation_cache_key, {
                "user_id": user_id,
                "litellm_key_prefix": litellm_key[:8] + "...",
                "validated_at": time.time()
            }, ttl=300)  # 5 minutes cache for validation
        except Exception as cache_error:
            logger.debug(
                "Failed to cache proxy validation",
                user_id=user_id,
                error=str(cache_error)
            )
        
    except Exception as e:
        logger.error(
            "Failed to get user LiteLLM key from Supabase",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve user LiteLLM key", "detail": str(e)}
        )
    
    # Add user context for billing
    enhanced_request = request_body.copy()
    enhanced_request["user"] = user_id  # For billing attribution
    
    # Add metadata
    if "metadata" not in enhanced_request:
        enhanced_request["metadata"] = {}
    enhanced_request["metadata"].update({
        "gateway_version": llm_client.settings.version,
        "user_id": user_id,
        "request_timestamp": time.time()
    })
    
    logger.debug(
        "Enhanced request prepared",
        user_id=user_id,
        model=model,
        request_keys=list(enhanced_request.keys())
    )
    
    # Make direct request to LLM service
    start_time = time.time()
    
    try:
        # Add LiteLLM API key to headers
        headers = {
            "Authorization": f"Bearer {litellm_key}",
            # CRITICAL: Disable compression for streaming
            "Accept-Encoding": "identity"
        }
        
        # Check if this is a streaming request
        is_streaming = enhanced_request.get("stream", False)
        
        if is_streaming:
            # Handle streaming response with TRUE transparent proxying
            logger.debug(
                "Streaming request started",
                user_id=user_id,
                model=model
            )
            
            async def stream_generator():
                try:
                    logger.debug(
                        "Opening upstream connection with no buffering",
                        user_id=user_id,
                        model=model
                    )
                    
                    # CRITICAL: Use stream() with explicit no-buffering settings
                    async with llm_client.client.stream(
                        "POST",
                        "/chat/completions",
                        json=enhanced_request,
                        headers=headers
                    ) as response:
                        duration = time.time() - start_time
                        
                        # Record metrics
                        from src.utils.metrics import metrics
                        metrics.record_upstream_request("litellm", response.status_code, duration)
                        
                        logger.debug(
                            "Upstream connection established",
                            user_id=user_id,
                            model=model,
                            status_code=response.status_code,
                            duration_ms=round(duration * 1000, 2)
                        )
                        
                        # Handle errors by streaming them immediately
                        if response.status_code >= 400:
                            logger.error(
                                "=== UPSTREAM ERROR RESPONSE ===",
                                user_id=user_id,
                                model=model,
                                status_code=response.status_code
                            )
                            
                            # Stream error response without buffering
                            async for chunk in response.aiter_bytes(chunk_size=1024):
                                if chunk:
                                    yield chunk
                            return
                        
                        # For successful responses, TRUE streaming without any buffering
                        logger.debug(
                            "Starting stream forwarding",
                            user_id=user_id,
                            model=model
                        )
                        
                        chunk_count = 0
                        total_bytes = 0
                        last_log_time = time.time()
                        last_ping_time = time.time()
                        
                        async for chunk in response.aiter_bytes(chunk_size=settings.stream_chunk_size):
                            if chunk:
                                chunk_count += 1
                                total_bytes += len(chunk)
                                
                                # IMMEDIATELY yield each chunk without any processing
                                yield chunk
                                
                                current_time = time.time()
                                
                                # Send keep-alive pings every configured interval
                                if current_time - last_ping_time > settings.stream_keepalive_interval:
                                    logger.debug(
                                        "Sending keep-alive ping",
                                        user_id=user_id,
                                        model=model
                                    )
                                    yield b": ping\n\n"
                                    last_ping_time = current_time
                                
                                # Log progress every 5 seconds or every 50 chunks
                                if (current_time - last_log_time > 5.0) or (chunk_count % 50 == 0):
                                    logger.info(
                                        "=== STREAMING PROGRESS ===",
                                        user_id=user_id,
                                        model=model,
                                        chunks_yielded=chunk_count,
                                        total_bytes=total_bytes,
                                        elapsed_time=round(current_time - start_time, 2)
                                    )
                                    last_log_time = current_time
                        
                        logger.debug(
                            "Streaming completed",
                            user_id=user_id,
                            model=model,
                            total_chunks=chunk_count,
                            total_bytes=total_bytes,
                            duration=round(time.time() - start_time, 2)
                        )
                                
                except Exception as e:
                    logger.error(
                        "=== STREAMING ERROR ===",
                        user_id=user_id,
                        model=model,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True
                    )
                    # Yield error in SSE format
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache, no-transform, no-store",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Transfer-Encoding": "chunked",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY"
                }
            )
        
        else:
            # Handle non-streaming response
            response = await llm_client.client.post(
                "/chat/completions",
                json=enhanced_request,
                headers=headers
            )
            
            duration = time.time() - start_time
            
            # Record metrics
            from src.utils.metrics import metrics
            metrics.record_upstream_request("litellm", response.status_code, duration)
            
            # Log request
            logger.debug(
                "LLM proxy request completed",
                user_id=user_id,
                model=model,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
            
            # Return response as-is (including errors from LLM service)
            if response.status_code >= 400:
                # For errors, return the error response from LLM service
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = {"error": response.text}
                
                return JSONResponse(
                    status_code=response.status_code,
                    content=error_detail
                )
            
            # For successful responses, sanitize and return
            response_data = response.json()
            
            # Sanitize usage data to fix Gemini null cached_tokens issue
            if "usage" in response_data and response_data["usage"]:
                usage = response_data["usage"]
                
                # Fix prompt_tokens_details.cached_tokens if it's null or missing
                if "prompt_tokens_details" in usage and usage["prompt_tokens_details"]:
                    prompt_details = usage["prompt_tokens_details"]
                    if "cached_tokens" in prompt_details and prompt_details["cached_tokens"] is None:
                        prompt_details["cached_tokens"] = 0
                    elif "cached_tokens" not in prompt_details:
                        prompt_details["cached_tokens"] = 0
                
                # Ensure all token counts are integers
                for key in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                    if key in usage and usage[key] is None:
                        usage[key] = 0
            
            # Log usage for billing
            usage = response_data.get("usage", {})
            logger.info(
                "LLM request completed",
                user_id=user_id,
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0)
            )
            
            logger.info(
                "=== LLM PROXY REQUEST SUCCESS ===",
                user_id=user_id,
                model=model,
                status_code=response.status_code
            )
            
            return JSONResponse(
                status_code=response.status_code,
                content=response_data
            )
        
    except Exception as e:
        logger.error(
            "=== LLM PROXY REQUEST FAILED ===",
            user_id=user_id,
            model=model,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        
        return JSONResponse(
            status_code=500,
            content={"error": "Internal proxy error", "detail": str(e), "error_type": type(e).__name__}
        )