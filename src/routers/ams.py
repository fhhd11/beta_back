"""
AMS (Agent Management Service) proxy router.
Provides a unified interface for all AMS operations.
"""

import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
import structlog

from src.dependencies.auth import get_current_user_id
from src.services.ams_client import get_ams_client

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    summary="AMS Proxy",
    description="Unified proxy for all AMS operations with path rewriting and security filtering",
    operation_id="ams_proxy_catch_all"
)
async def ams_proxy(
    request: Request,
    path: str,
    user_id: str = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Proxy all AMS requests with proper authentication and error handling.
    
    Features:
    - Automatic user ID injection from JWT
    - Idempotency support
    - Request/response logging
    - Error handling and transformation
    - Security filtering
    """
    logger.info(
        "AMS proxy request",
        method=request.method,
        path=path,
        user_id=user_id,
        idempotency_key=idempotency_key
    )
    
    try:
        # Get AMS client
        ams_client = await get_ams_client()
        
        # Read request body if present
        body = None
        content_type = request.headers.get("content-type", "")
        
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
            except Exception as e:
                logger.warning("Failed to read request body", error=str(e))
        
        # Prepare headers for AMS request
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        
        # Parse JSON data if present
        json_data = None
        if body and content_type.startswith('application/json'):
            try:
                json_data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON body", body=body.decode('utf-8', errors='ignore'))
                raise HTTPException(status_code=400, detail="Invalid JSON in request body")
        
        # Forward the request to AMS
        # Note: AMS Edge function expects paths without /ams prefix
        response = await ams_client._make_request(
            method=request.method,
            path=f"/{path}",  # Direct path to AMS Edge function
            user_id=user_id,
            headers=headers,
            json_data=json_data
        )
        
        # Get response data
        response_data = response.content
        status_code = response.status_code
        response_headers = dict(response.headers)
        
        # Remove any sensitive headers
        response_headers.pop("authorization", None)
        response_headers.pop("x-user-id", None)
        # Remove Content-Length to let FastAPI/uvicorn calculate it automatically
        response_headers.pop("content-length", None)
        
        logger.info(
            "AMS proxy response",
            status_code=status_code,
            content_length=len(response_data) if response_data else 0
        )
        
        # Return response
        return Response(
            content=response_data,
            status_code=status_code,
            headers=response_headers,
            media_type=response_headers.get("content-type", "application/json")
        )
        
    except Exception as e:
        logger.error(
            "AMS proxy error",
            error=str(e),
            method=request.method,
            path=path,
            user_id=user_id
        )
        
        # Transform AMS errors to standard HTTP errors
        if hasattr(e, 'status_code'):
            raise HTTPException(
                status_code=e.status_code,
                detail=str(e)
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Internal server error"
            )


# Specific endpoints for better documentation and type safety
@router.get(
    "/health",
    summary="AMS Health Check",
    description="Check AMS service health"
)
async def ams_health():
    """Check AMS service health."""
    ams_client = await get_ams_client()
    
    try:
        response = await ams_client._make_request(
            method="GET",
            path="/health"
        )
        return response.json()
    except Exception as e:
        logger.error("AMS health check failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="AMS service unavailable"
        )


@router.get(
    "/me",
    summary="Get User Profile",
    description="Get user profile and agent information from AMS"
)
async def get_user_profile(
    user_id: str = Depends(get_current_user_id)
):
    """Get user profile from AMS."""
    ams_client = await get_ams_client()
    return await ams_client.get_user_profile(user_id)


@router.post(
    "/agents/create",
    summary="Create Agent",
    description="Create a new agent via AMS"
)
async def create_agent(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Create a new agent via AMS."""
    ams_client = await get_ams_client()
    
    # Read and validate request body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is required")
    
    try:
        import json
        request_data = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    
    # Validate required fields
    if not request_data.get('template_id'):
        raise HTTPException(status_code=400, detail="template_id is required")
    
    # Prepare headers
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    
    # Forward to AMS
    response = await ams_client._make_request(
        method="POST",
        path="/agents/create",
        user_id=user_id,
        headers=headers,
        json_data=request_data
    )
    
    return response.json()


@router.post(
    "/agents/{agent_id}/upgrade",
    summary="Upgrade Agent",
    description="Upgrade an agent to a new version"
)
async def upgrade_agent(
    agent_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Upgrade an agent via AMS."""
    ams_client = await get_ams_client()
    
    # Read request body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is required")
    
    try:
        import json
        request_data = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    
    # Validate required fields
    if not request_data.get('target_version'):
        raise HTTPException(status_code=400, detail="target_version is required")
    
    # Prepare headers
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    
    # Forward to AMS
    response = await ams_client._make_request(
        method="POST",
        path=f"/agents/{agent_id}/upgrade",
        user_id=user_id,
        headers=headers,
        json_data=request_data
    )
    
    return response.json()


@router.post(
    "/templates/validate",
    summary="Validate Template",
    description="Validate template content via AMS"
)
async def validate_template(
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Validate template content via AMS."""
    ams_client = await get_ams_client()
    
    # Read request body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is required")
    
    # Forward to AMS (templates/validate doesn't need user_id)
    response = await ams_client._make_request(
        method="POST",
        path="/templates/validate",
        json_data=body.decode('utf-8')
    )
    
    return response.json()


@router.post(
    "/templates/publish",
    summary="Publish Template",
    description="Publish template via AMS"
)
async def publish_template(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Publish template via AMS."""
    ams_client = await get_ams_client()
    
    # Read request body
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is required")
    
    # Prepare headers
    headers = {}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    
    # Forward to AMS
    response = await ams_client._make_request(
        method="POST",
        path="/templates/publish",
        user_id=user_id,
        headers=headers,
        json_data=body.decode('utf-8')
    )
    
    return response.json()
