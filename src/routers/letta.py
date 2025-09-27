"""
Simple Letta proxy router - direct pass-through with blacklist filtering.
"""

import re
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
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
            }
        )
    
    return _letta_client

def is_blacklisted(path: str) -> bool:
    """Check if path is blacklisted."""
    for pattern in BLACKLISTED_PATTERNS:
        if re.match(pattern, path):
            return True
    return False

@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
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
    - Direct pass-through of requests/responses
    """
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
    
    logger.info(
        "Letta proxy request",
        method=request.method,
        path=letta_path,
        user_id=user_id
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
        
        # Make request to Letta
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