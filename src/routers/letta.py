"""
Simple Letta proxy router - direct pass-through with blacklist filtering and streaming support.
"""

import re
import time
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
import httpx
import structlog

from src.dependencies.auth import get_current_user_id
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()

# Blacklisted operations (security filtering)
BLACKLISTED_PATTERNS = [
    r"^/v1/agents$",                    # POST - создание агентов (только через AMS)
    r"^/v1/agents/[^/]+$",             # PUT/DELETE - редактирование/удаление агентов (только через AMS)
    r"^/admin/.*$",                    # Админские функции
    r"^/users/.*$",                    # Пользовательские функции
]

# Streaming endpoints patterns
STREAMING_PATTERNS = [
    r"^/v1/agents/[^/]+/messages/stream$",    # Message streaming
    r"^/v1/agents/[^/]+/runs/[^/]+/stream$",  # Run streaming
    r"^/v1/agents/[^/]+/messages/stream.*$",  # Message streaming with params
    r"^/v1/agents/[^/]+/runs/[^/]+/stream.*$",  # Run streaming with params
]

# HTTP client for Letta
_letta_client: httpx.AsyncClient = None

async def get_letta_client() -> httpx.AsyncClient:
    """Get or create Letta HTTP client."""
    global _letta_client
    
    if _letta_client is None:
        _letta_client = httpx.AsyncClient(
            base_url=str(settings.letta_base_url).rstrip('/'),
            timeout=httpx.Timeout(settings.letta_timeout),
            headers={
                "Authorization": f"Bearer {settings.letta_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            # Disable response buffering for streaming
            follow_redirects=True
        )
    
    return _letta_client

def is_blacklisted(path: str) -> bool:
    """Check if path is blacklisted."""
    for pattern in BLACKLISTED_PATTERNS:
        if re.match(pattern, path):
            return True
    return False

def is_streaming_endpoint(path: str) -> bool:
    """Check if path is a streaming endpoint."""
    for pattern in STREAMING_PATTERNS:
        if re.match(pattern, path):
            logger.debug(
                "Streaming pattern matched",
                path=path,
                pattern=pattern
            )
            return True
    logger.debug(
        "No streaming pattern matched",
        path=path,
        patterns=STREAMING_PATTERNS
    )
    return False

@router.get("/debug/test")
async def debug_test():
    """Simple test endpoint to verify our code is running."""
    return {
        "message": "Letta router is working!",
        "timestamp": time.time(),
        "streaming_patterns": STREAMING_PATTERNS
    }

@router.get("/debug/streaming-patterns")
async def debug_streaming_patterns():
    """Debug endpoint to check streaming patterns."""
    return {
        "streaming_patterns": STREAMING_PATTERNS,
        "blacklisted_patterns": BLACKLISTED_PATTERNS,
        "stream_tokens_support": {
            "description": "stream_tokens parameter enables token-level streaming",
            "supported_in": "request body (json_data.stream_tokens) or query params",
            "chunk_size": "64 bytes for token streaming, 1024 bytes for regular streaming"
        },
        "test_paths": [
            "/v1/agents/test-agent/messages/stream",
            "/v1/agents/test-agent/runs/test-run/stream",
            "/v1/agents/test-agent/messages/stream?stream_tokens=true",
        ],
        "test_results": {
            path: {
                "is_streaming": is_streaming_endpoint(path),
                "is_blacklisted": is_blacklisted(path),
                "has_stream_tokens_param": "stream_tokens=true" in path
            }
            for path in [
                "/v1/agents/test-agent/messages/stream",
                "/v1/agents/test-agent/runs/test-run/stream",
                "/v1/agents/test-agent/messages",
                "/v1/agents/test-agent/messages/stream?stream_tokens=true",
            ]
        }
    }


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    summary="Letta Proxy",
    description="Direct proxy to Letta API with blacklist filtering"
)
async def letta_proxy(
    request: Request,
    path: str,
    user_id: str = Depends(get_current_user_id)
):
    logger.critical("🔵🔵🔵 LETTA PROXY CALLED - NEW VERSION 2025-10-05 17:35 🔵🔵🔵")
    logger.critical(f"🔵🔵🔵 LETTA PROXY CALLED - PATH: {path} 🔵🔵🔵")
    logger.critical(f"🔵🔵🔵 LETTA PROXY CALLED - FULL URL: {request.url} 🔵🔵🔵")
    logger.critical(f"🔵🔵🔵 LETTA PROXY CALLED - METHOD: {request.method} 🔵🔵🔵")
    """
    Simple Letta proxy that forwards requests directly to Letta API.
    
    Features:
    - JWT authentication check
    - Path rewriting: /api/v1/letta/* -> /v1/*
    - Blacklist filtering for security
    - Streaming support for streaming endpoints
    - Direct pass-through of requests/responses
    """
    print("🔵🔵🔵 LETTA PROXY CALLED 🔵🔵🔵")
    logger.info(
        "Letta proxy called",
        method=request.method,
        path=path,
        full_url=str(request.url),
        user_id=user_id
    )
    
    # Rewrite path: /api/v1/letta/agents -> /v1/agents
    letta_path = f"/v1/{path}" if path else "/v1/"
    
    # Check blacklist
    if is_blacklisted(letta_path):
        logger.warning(
            "Blocked blacklisted Letta operation",
            method=request.method,
            path=letta_path,
            user_id=user_id
        )
        raise HTTPException(
            status_code=403,
            detail=f"Operation not allowed: {request.method} {letta_path}"
        )
    
    # Check if this is a streaming endpoint
    is_streaming = is_streaming_endpoint(letta_path)
    
    # Debug logging for streaming detection
    logger.info(
        "Streaming endpoint detection",
        letta_path=letta_path,
        is_streaming=is_streaming,
        patterns=STREAMING_PATTERNS,
        user_id=user_id
    )
    
    # Prepare request data early for stream_tokens check
    json_data = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            json_data = await request.json()
        except Exception:
            json_data = None
    
    # Check if stream_tokens is enabled (for token-level streaming)
    stream_tokens = False
    if json_data and isinstance(json_data, dict):
        stream_tokens = json_data.get("stream_tokens", False)
    
    # Also check query params for stream_tokens (backward compatibility)
    if not stream_tokens:
        stream_tokens = request.query_params.get("stream_tokens", "").lower() == "true"
    
    # Ensure stream_tokens is passed to Letta API in request body
    if stream_tokens and json_data and isinstance(json_data, dict):
        json_data["stream_tokens"] = True
    elif stream_tokens and not json_data:
        # If no JSON data but stream_tokens is in query params, create JSON data
        json_data = {"stream_tokens": True}
    
    logger.info(
        "Letta proxy request",
        method=request.method,
        path=letta_path,
        user_id=user_id,
        is_streaming=is_streaming,
        stream_tokens=stream_tokens,
        json_data_keys=list(json_data.keys()) if json_data and isinstance(json_data, dict) else None,
        query_params=dict(request.query_params)
    )
    
    try:
        # Get Letta client
        letta_client = await get_letta_client()
        
        # Prepare headers (exclude auth headers)
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ["authorization", "host", "content-length"]:
                headers[key] = value
        
        # Add user context
        headers["X-User-Id"] = user_id
        
        # For streaming requests, ensure proper headers
        if is_streaming:
            headers["Accept"] = "text/event-stream"
            headers["Cache-Control"] = "no-cache"
            
            # For token-level streaming, add specific headers
            if stream_tokens:
                headers["Accept"] = "text/event-stream"
                headers["X-Stream-Tokens"] = "true"
        
        # Handle streaming vs regular requests
        if is_streaming:
            logger.info(
                "Entering streaming mode",
                path=letta_path,
                user_id=user_id,
                stream_tokens=stream_tokens
            )
            # Streaming mode
            async def stream_response():
                try:
                    async with letta_client.stream(
                        method=request.method,
                        url=letta_path,
                        headers=headers,
                        json=json_data,
                        params=dict(request.query_params)
                    ) as response:
                        # Check response status
                        if response.status_code >= 400:
                            logger.error(
                                "Letta streaming error",
                                status_code=response.status_code,
                                path=letta_path,
                                user_id=user_id
                            )
                            yield f"data: {response.text}\n\n".encode()
                            return
                        
                        # Stream response chunks immediately
                        chunk_count = 0
                        total_bytes = 0
                        start_time = time.time()
                        
                        logger.info(
                            "Starting stream forwarding",
                            path=letta_path,
                            user_id=user_id,
                            stream_tokens=stream_tokens,
                            content_type=response.headers.get("content-type"),
                            transfer_encoding=response.headers.get("transfer-encoding"),
                            response_headers=dict(response.headers),
                            status_code=response.status_code
                        )
                        
                        if stream_tokens:
                            # For token streaming, pass data as-is without chunking
                            # Let Letta API handle the token boundaries
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    chunk_count += 1
                                    total_bytes += len(chunk)
                                    
                                    # Log first chunk for debugging
                                    if chunk_count == 1:
                                        logger.info(
                                            "First token streaming chunk",
                                            chunk_size=len(chunk),
                                            chunk_preview=chunk[:100].decode('utf-8', errors='ignore'),
                                            path=letta_path,
                                            user_id=user_id
                                        )
                                    
                                    logger.debug(
                                        "Token streaming chunk",
                                        chunk_size=len(chunk),
                                        chunk_count=chunk_count,
                                        total_bytes=total_bytes,
                                        path=letta_path,
                                        user_id=user_id,
                                        stream_tokens=stream_tokens
                                    )
                                    yield chunk
                        else:
                            # For regular streaming, use smaller chunk size for better responsiveness
                            async for chunk in response.aiter_bytes(chunk_size=512):
                                if chunk:
                                    chunk_count += 1
                                    total_bytes += len(chunk)
                                    
                                    # Log first chunk for debugging
                                    if chunk_count == 1:
                                        logger.info(
                                            "First regular streaming chunk",
                                            chunk_size=len(chunk),
                                            chunk_preview=chunk[:100].decode('utf-8', errors='ignore'),
                                            path=letta_path,
                                            user_id=user_id
                                        )
                                    
                                    logger.debug(
                                        "Regular streaming chunk",
                                        chunk_size=len(chunk),
                                        chunk_count=chunk_count,
                                        total_bytes=total_bytes,
                                        path=letta_path,
                                        user_id=user_id,
                                        stream_tokens=stream_tokens
                                    )
                                    yield chunk
                        
                        duration = time.time() - start_time
                        
                        # Log warning if no data was streamed
                        if chunk_count == 0:
                            logger.warning(
                                "Streaming completed with no data",
                                path=letta_path,
                                user_id=user_id,
                                stream_tokens=stream_tokens,
                                duration_seconds=round(duration, 2),
                                response_status=response.status_code,
                                content_type=response.headers.get("content-type")
                            )
                        else:
                            logger.info(
                                "Streaming completed",
                                total_chunks=chunk_count,
                                total_bytes=total_bytes,
                                duration_seconds=round(duration, 2),
                                bytes_per_second=round(total_bytes / duration, 2) if duration > 0 else 0,
                                path=letta_path,
                                user_id=user_id,
                                stream_tokens=stream_tokens,
                                streaming_mode="token-level" if stream_tokens else "regular"
                            )
                                
                except httpx.ConnectError as e:
                    logger.error(
                        "Letta connection error",
                        path=letta_path,
                        user_id=user_id,
                        error=str(e),
                        error_type="ConnectError"
                    )
                    yield f"data: {{'error': 'Connection to Letta API failed. Please try again.'}}\n\n".encode()
                except httpx.TimeoutException as e:
                    logger.error(
                        "Letta timeout error",
                        path=letta_path,
                        user_id=user_id,
                        error=str(e),
                        error_type="TimeoutException"
                    )
                    yield f"data: {{'error': 'Letta API request timed out. Please try again.'}}\n\n".encode()
                except Exception as e:
                    logger.error(
                        "Streaming error",
                        path=letta_path,
                        user_id=user_id,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    yield f"data: {{'error': 'Streaming failed: {str(e)}'}}\n\n".encode()
            
            # Prepare response headers
            response_headers = {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "X-Content-Type-Options": "nosniff",
                "Transfer-Encoding": "chunked",
            }
            
            # Add token streaming specific headers
            if stream_tokens:
                response_headers["X-Stream-Tokens"] = "true"
            
            return StreamingResponse(
                stream_response(),
                status_code=200,
                headers=response_headers
            )
        else:
            # Regular mode
            logger.info(
                "Entering regular mode (non-streaming)",
                path=letta_path,
                user_id=user_id,
                is_streaming=is_streaming
            )
            response = await letta_client.request(
                method=request.method,
                url=letta_path,
                headers=headers,
                json=json_data,
                params=dict(request.query_params)
            )
            
            # Return response directly
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ["content-length", "transfer-encoding"]
                },
                media_type=response.headers.get("content-type")
            )
        
    except httpx.TimeoutException as e:
        logger.error(
            "Letta request timeout", 
            path=letta_path, 
            user_id=user_id, 
            error=str(e),
            error_type="TimeoutException"
        )
        raise HTTPException(status_code=504, detail="Letta service timeout")
    
    except httpx.ConnectError as e:
        logger.error(
            "Letta connection error", 
            path=letta_path, 
            user_id=user_id, 
            error=str(e),
            error_type="ConnectError"
        )
        raise HTTPException(status_code=502, detail="Letta service unavailable - connection failed")
    
    except httpx.RequestError as e:
        logger.error(
            "Letta request error", 
            path=letta_path, 
            user_id=user_id, 
            error=str(e),
            error_type="RequestError"
        )
        raise HTTPException(status_code=502, detail="Letta service unavailable")
    
    except Exception as e:
        logger.error(
            "Letta proxy error", 
            path=letta_path, 
            user_id=user_id, 
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/health")
async def letta_health():
    """Health check for Letta service."""
    try:
        letta_client = await get_letta_client()
        response = await letta_client.get("/health")
        
        if response.status_code == 200:
            return {"status": "healthy", "letta_health": response.json()}
        else:
            raise HTTPException(status_code=503, detail="Letta service unhealthy")
            
    except Exception as e:
        logger.error("Letta health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Letta service unavailable")
