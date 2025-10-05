"""
Agent management endpoints (AMS proxy).
"""

from typing import Optional
from fastapi import APIRouter, Request, Depends, Header
import structlog

from src.dependencies.auth import get_current_user_id
from src.services.ams_client import get_ams_client
from src.models.requests import CreateAgentRequest, UpgradeAgentRequest
from src.models.responses import AgentInstance, AgentSummary

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/create",
    response_model=AgentInstance,
    summary="Create Agent",
    description="Create a new agent via AMS with optional idempotency support"
)
async def create_agent(
    request: Request,
    agent_request: CreateAgentRequest,
    user_id: str = Depends(get_current_user_id),
    x_idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Create a new agent through AMS.
    
    Features:
    - Automatic user ID extraction from JWT
    - Idempotency support via X-Idempotency-Key header
    - Full validation of agent configuration
    """
    logger.info(
        "Creating agent",
        user_id=user_id,
        agent_name=agent_request.agent_name,
        template_id=agent_request.template_id,
        idempotency_key=x_idempotency_key
    )
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Create agent
    agent = await ams_client.create_agent(
        user_id=user_id,
        request_data=agent_request,
        idempotency_key=x_idempotency_key
    )
    
    logger.info(
        "Agent created successfully",
        user_id=user_id,
        agent_id=agent.agent_id,
        agent_name=agent.name
    )
    
    return agent


@router.post(
    "/{agent_id}/upgrade",
    response_model=AgentInstance,
    summary="Upgrade Agent",
    description="Upgrade an agent to a new version with optional configuration updates"
)
async def upgrade_agent(
    agent_id: str,
    upgrade_request: UpgradeAgentRequest,
    user_id: str = Depends(get_current_user_id),
    x_idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Upgrade an agent to a new version.
    
    Features:
    - Ownership validation
    - Version management
    - Memory preservation options
    - Configuration updates
    """
    logger.info(
        "Upgrading agent",
        user_id=user_id,
        agent_id=agent_id,
        target_version=upgrade_request.target_version,
        preserve_memory=upgrade_request.preserve_memory,
        idempotency_key=x_idempotency_key
    )
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Upgrade agent
    agent = await ams_client.upgrade_agent(
        user_id=user_id,
        agent_id=agent_id,
        request_data=upgrade_request,
        idempotency_key=x_idempotency_key
    )
    
    logger.info(
        "Agent upgraded successfully",
        user_id=user_id,
        agent_id=agent_id,
        new_version=agent.metadata.get("version") if agent.metadata else None
    )
    
    return agent


@router.get(
    "/{agent_id}",
    response_model=AgentInstance,
    summary="Get Agent Details",
    description="Get detailed information about a specific agent"
)
async def get_agent_details(
    agent_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Get detailed agent information."""
    logger.info("Getting agent details", user_id=user_id, agent_id=agent_id)
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # Get agent details
    agent = await ams_client.get_agent_details(user_id, agent_id)
    
    return agent


@router.get(
    "",
    response_model=list[AgentSummary],
    summary="List User Agents",
    description="Get list of all agents owned by the current user"
)
async def list_user_agents(
    user_id: str = Depends(get_current_user_id)
):
    """List all agents for the current user."""
    logger.info("Listing user agents", user_id=user_id)
    
    # Get AMS client
    ams_client = await get_ams_client()
    
    # List agents
    agents = await ams_client.list_user_agents(user_id)
    
    logger.info(
        "User agents listed",
        user_id=user_id,
        agents_count=len(agents)
    )
    
    return agents
