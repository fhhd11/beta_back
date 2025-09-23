"""
Unified Letta proxy router with path rewriting and security filtering.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import structlog

from src.dependencies.auth import get_current_user_id
from src.services.letta_client import get_letta_client
from src.models.requests import SendMessageRequest, UpdateMemoryRequest, ArchivalMemoryRequest
from src.models.responses import LettaAgent, LettaMessage

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    summary="Unified Letta Proxy",
    description="Intelligent proxy for all Letta operations with path rewriting and security filtering"
)
async def letta_proxy(
    request: Request,
    path: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Unified Letta proxy endpoint that handles all Letta operations.
    
    Features:
    - Path rewriting from /api/v1/letta/* to /v1/*
    - Security filtering (whitelist/blacklist)
    - Automatic user ownership validation
    - Response filtering to hide internal fields
    """
    method = request.method
    full_path = f"/api/v1/letta/{path}" if path else "/api/v1/letta/"
    
    logger.info(
        "Letta proxy request",
        method=method,
        path=full_path,
        user_id=user_id
    )
    
    # Get request data
    json_data = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            json_data = await request.json()
        except Exception:
            json_data = None
    
    # Get query parameters
    params = dict(request.query_params)
    
    # Get headers (filter out auth headers)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ["authorization", "host", "content-length"]:
            headers[key] = value
    
    try:
        # Get Letta client
        letta_client = await get_letta_client()
        
        # Proxy the request
        result = await letta_client.proxy_request(
            method=method,
            path=full_path,
            user_id=user_id,
            headers=headers,
            json_data=json_data,
            params=params
        )
        
        # Return response
        return JSONResponse(
            status_code=result["status_code"],
            content=result["data"],
            headers={k: v for k, v in result["headers"].items() 
                    if k.lower() not in ["content-length", "transfer-encoding"]}
        )
        
    except Exception as e:
        logger.error(
            "Letta proxy error",
            method=method,
            path=full_path,
            user_id=user_id,
            error=str(e)
        )
        raise


# Specific endpoints for better documentation and type safety
@router.get(
    "/agents",
    response_model=list[LettaAgent],
    summary="List Letta Agents",
    description="Get list of all Letta agents owned by the user"
)
async def list_letta_agents(
    user_id: str = Depends(get_current_user_id)
):
    """List all Letta agents for the current user."""
    letta_client = await get_letta_client()
    return await letta_client.list_agents(user_id)


@router.get(
    "/agents/{agent_id}",
    response_model=LettaAgent,
    summary="Get Letta Agent",
    description="Get detailed information about a specific Letta agent"
)
async def get_letta_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Get specific Letta agent details."""
    letta_client = await get_letta_client()
    return await letta_client.get_agent(user_id, agent_id)


@router.post(
    "/agents/{agent_id}/messages",
    summary="Send Message to Letta Agent",
    description="Send a message to a Letta agent and get the response"
)
async def send_message_to_letta_agent(
    agent_id: str,
    message_request: SendMessageRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Send message to Letta agent."""
    letta_client = await get_letta_client()
    return await letta_client.send_message(user_id, agent_id, message_request)


@router.get(
    "/agents/{agent_id}/messages",
    response_model=list[LettaMessage],
    summary="Get Agent Messages",
    description="Get message history for a Letta agent"
)
async def get_letta_agent_messages(
    agent_id: str,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    user_id: str = Depends(get_current_user_id)
):
    """Get message history for Letta agent."""
    letta_client = await get_letta_client()
    return await letta_client.get_messages(user_id, agent_id, limit, offset)


@router.get(
    "/agents/{agent_id}/memory",
    summary="Get Agent Memory",
    description="Get memory state of a Letta agent"
)
async def get_letta_agent_memory(
    agent_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Get Letta agent memory."""
    letta_client = await get_letta_client()
    return await letta_client.get_memory(user_id, agent_id)


@router.put(
    "/agents/{agent_id}/memory",
    summary="Update Agent Memory",
    description="Update memory state of a Letta agent"
)
async def update_letta_agent_memory(
    agent_id: str,
    memory_request: UpdateMemoryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Update Letta agent memory."""
    letta_client = await get_letta_client()
    return await letta_client.update_memory(user_id, agent_id, memory_request)


@router.get(
    "/agents/{agent_id}/archival",
    summary="Get Agent Archival Memory",
    description="Search and retrieve archival memory for a Letta agent"
)
async def get_letta_agent_archival_memory(
    agent_id: str,
    query: Optional[str] = None,
    limit: Optional[int] = 10,
    user_id: str = Depends(get_current_user_id)
):
    """Get Letta agent archival memory."""
    letta_client = await get_letta_client()
    return await letta_client.get_archival_memory(user_id, agent_id, query, limit)


@router.post(
    "/agents/{agent_id}/archival",
    summary="Add to Agent Archival Memory",
    description="Add new content to a Letta agent's archival memory"
)
async def add_to_letta_agent_archival_memory(
    agent_id: str,
    archival_request: ArchivalMemoryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Add to Letta agent archival memory."""
    letta_client = await get_letta_client()
    return await letta_client.add_archival_memory(user_id, agent_id, archival_request)


@router.get("/health")
async def letta_health():
    """Health check for Letta service using official /health endpoint."""
    try:
        letta_client = await get_letta_client()
        health_result = await letta_client.health_check()
        
        if health_result["status"] == "healthy":
            return {
                "status": "healthy",
                "letta_health": health_result
            }
        else:
            logger.error("Letta health check failed", result=health_result)
            raise HTTPException(
                status_code=503, 
                detail=f"Letta service unhealthy: {health_result}"
            )
    except Exception as e:
        logger.error("Letta health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Letta service unavailable")


@router.get("/test-paths")
async def test_letta_paths(current_user: User = Depends(get_current_user)):
    """Test different Letta API paths to understand the correct format."""
    letta_client = await get_letta_client()
    
    # Test paths based on official Letta API documentation
    # https://docs.letta.com/api-reference/overview
    test_paths = [
        "/health",  # Official health check endpoint
        "/agents",  # Official agents list endpoint
        "/",        # Root endpoint
        f"/agents/{current_user.id}",  # User-specific agent access
        "/models",  # Models endpoint
        "/blocks",  # Blocks endpoint
        "/tools",   # Tools endpoint
    ]
    
    results = {}
    for path in test_paths:
        try:
            response = await letta_client._make_request("GET", path, user_id=current_user.id)
            results[path] = {
                "status_code": response.status_code,
                "success": response.status_code < 400
            }
        except Exception as e:
            results[path] = {
                "status_code": None,
                "success": False,
                "error": str(e)
            }
    
    # Also test the official health endpoint
    health_result = await letta_client.health_check()
    
    return {
        "user_id": current_user.id,
        "base_url": letta_client.base_url,
        "health_check": health_result,
        "test_results": results
    }