"""
Simple Letta proxy router - direct pass-through with blacklist filtering and streaming support.
"""

import re
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
            return True
    return False

@router.get("/debug/streaming-patterns")
async def debug_streaming_patterns():
    """Debug endpoint to check streaming patterns."""
    return {
        "streaming_patterns": STREAMING_PATTERNS,
        "blacklisted_patterns": BLACKLISTED_PATTERNS,
        "test_paths": [
            "/v1/agents/test-agent/messages/stream",
            "/v1/agents/test-agent/runs/test-run/stream",
            "/v1/agents/test-agent/messages/stream?stream_tokens=true",
        ],
        "test_results": {
            path: {
                "is_streaming": is_streaming_endpoint(path),
                "is_blacklisted": is_blacklisted(path)
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
    """
    Simple Letta proxy that forwards requests directly to Letta API.
    
    Features:
    - JWT authentication check
    - Path rewriting: /api/v1/letta/* -> /v1/*
    - Blacklist filtering for security
    - Streaming support for streaming endpoints
    - Direct pass-through of requests/responses
    """
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
    
    logger.info(
        "Letta proxy request",
        method=request.method,
        path=letta_path,
        user_id=user_id,
        is_streaming=is_streaming
    )
    
    try:
        # Get Letta client
        letta_client = await get_letta_client()
        
        # Prepare request data
        json_data = None
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                json_data = await request.json()
            except Exception:
                json_data = None
        
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
        
        # Handle streaming vs regular requests
        if is_streaming:
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
                        async for chunk in response.aiter_bytes(chunk_size=1024):
                            if chunk:
                                chunk_count += 1
                                logger.debug(
                                    "Streaming chunk",
                                    chunk_size=len(chunk),
                                    chunk_count=chunk_count,
                                    path=letta_path,
                                    user_id=user_id
                                )
                                yield chunk
                        
                        logger.info(
                            "Streaming completed",
                            total_chunks=chunk_count,
                            path=letta_path,
                            user_id=user_id
                        )
                                
                except Exception as e:
                    logger.error(
                        "Streaming error",
                        path=letta_path,
                        user_id=user_id,
                        error=str(e)
                    )
                    yield f"data: {{'error': 'Streaming failed: {str(e)}'}}\n\n".encode()
            
            return StreamingResponse(
                stream_response(),
                status_code=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "*",
                }
            )
        else:
            # Regular mode
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
        
    except httpx.TimeoutException:
        logger.error("Letta request timeout", path=letta_path, user_id=user_id)
        raise HTTPException(status_code=504, detail="Letta service timeout")
    
    except httpx.RequestError as e:
        logger.error("Letta connection error", path=letta_path, user_id=user_id, error=str(e))
        raise HTTPException(status_code=502, detail="Letta service unavailable")
    
    except Exception as e:
        logger.error("Letta proxy error", path=letta_path, user_id=user_id, error=str(e))
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
