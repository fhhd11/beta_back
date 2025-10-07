"""
AMS (Agent Management Service) HTTP client with caching and error handling.
"""

import time
from typing import Dict, List, Optional, Any
import httpx
import structlog

from src.config.settings import get_settings
from src.models.requests import CreateAgentRequest, UpgradeAgentRequest
from src.models.responses import UserProfile, AgentInstance, AgentSummary
from src.utils.cache import cache_manager, cached_user_profile, cached_agent_ownership
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError, NotFoundError
from src.middleware.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = structlog.get_logger(__name__)


class AMSClient:
    """HTTP client for AMS (Agent Management Service) with caching and resilience."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.ams_base_url).rstrip('/')
        self.timeout = self.settings.request_timeout
        
        # Create circuit breaker for AMS service
        self.circuit_breaker = CircuitBreaker(
            CircuitBreakerConfig(service_name="ams")
        )
        
        # Configure HTTP client with Supabase service key
        try:
            # Try to enable HTTP/2 if h2 package is available
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=5.0,      # Connection timeout
                    read=self.timeout,  # Read timeout
                    write=5.0,        # Write timeout
                    pool=10.0         # Pool timeout
                ),
                headers={
                    "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.settings.supabase_service_key}"
                },
                limits=httpx.Limits(
                    max_keepalive_connections=50,  # Increased for better pooling
                    max_connections=200,           # Increased total connections
                    keepalive_expiry=30.0          # Keep connections alive longer
                ),
                http2=True,  # Enable HTTP/2 for better performance
                follow_redirects=True  # Handle redirects automatically
            )
        except ImportError:
            # Fallback to HTTP/1.1 if h2 package is not available
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=5.0,      # Connection timeout
                    read=self.timeout,  # Read timeout
                    write=5.0,        # Write timeout
                    pool=10.0         # Pool timeout
                ),
                headers={
                    "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.settings.supabase_service_key}"
                },
                limits=httpx.Limits(
                    max_keepalive_connections=50,  # Increased for better pooling
                    max_connections=200,           # Increased total connections
                    keepalive_expiry=30.0          # Keep connections alive longer
                ),
                http2=False,  # Disable HTTP/2 fallback
                follow_redirects=True  # Handle redirects automatically
            )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def _make_request(
        self,
        method: str,
        path: str,
        user_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        """Make HTTP request with error handling and metrics."""
        start_time = time.time()
        
        # Prepare headers
        request_headers = {}
        if user_id:
            request_headers["X-User-Id"] = user_id
        if headers:
            request_headers.update(headers)
        
        try:
            # Use circuit breaker for AMS requests
            if not await self.circuit_breaker.can_execute():
                raise UpstreamError("AMS service is currently unavailable (circuit breaker open)")
            
            response = await self.client.request(
                method=method,
                url=path,
                headers=request_headers,
                json=json_data,
                params=params
            )
            
            # Record success
            await self.circuit_breaker.record_success()
            
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_upstream_request("ams", response.status_code, duration)
            
            # Log request
            logger.debug(
                "AMS request completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
            
            # Handle error status codes
            if response.status_code >= 400:
                # Record failure for circuit breaker
                await self.circuit_breaker.record_failure()
                
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                if response.status_code == 404:
                    raise NotFoundError(
                        f"AMS resource not found: {path}",
                        context={"status_code": response.status_code, "detail": error_detail}
                    )
                else:
                    raise UpstreamError(
                        f"AMS request failed: {response.status_code}",
                        service_name="ams",
                        upstream_status=response.status_code,
                        context={"detail": error_detail}
                    )
            
            return response
            
        except httpx.TimeoutException:
            # Record failure for circuit breaker
            await self.circuit_breaker.record_failure()
            
            duration = time.time() - start_time
            metrics.record_upstream_request("ams", 408, duration)
            
            raise RequestTimeoutError(
                "AMS request timeout",
                timeout_seconds=self.timeout,
                context={"method": method, "path": path}
            )
        
        except httpx.RequestError as e:
            # Record failure for circuit breaker
            await self.circuit_breaker.record_failure()
            
            duration = time.time() - start_time
            metrics.record_upstream_request("ams", 502, duration)
            
            raise UpstreamError(
                f"AMS connection error: {str(e)}",
                service_name="ams",
                context={"method": method, "path": path, "error": str(e)}
            )
    
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Get user profile with agents from AMS."""
        logger.info("Fetching user profile from AMS", user_id=user_id)
        
        # Try cache first
        cache_key = f"ams_user_profile:{user_id}"
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            logger.info("AMS user profile cache hit", user_id=user_id, cached_data=cached_data)
            # Check if cached data is not empty
            if cached_data.get("email") or cached_data.get("letta_agent_id"):
                return UserProfile(**cached_data)
            else:
                logger.warning("Cached data is empty, fetching from AMS", user_id=user_id)
                # Clear empty cache
                await cache_manager.delete(cache_key)
        
        try:
            response = await self._make_request(
                method="GET",
                path="/me",  # Direct path to AMS endpoint
                user_id=user_id
            )
            
            logger.info(
                "AMS response received",
                user_id=user_id,
                status_code=response.status_code,
                response_text=response.text[:500] if response.text else "No response text"
            )
            
            data = response.json()
            
        except Exception as e:
            logger.warning(
                "AMS request failed, using fallback profile",
                user_id=user_id,
                error=str(e)
            )
            
            # Clear cache to prevent stale data
            await cache_manager.delete(cache_key)
            
            # Return fallback profile with minimal data
            return UserProfile(
                user_id=user_id,
                email=None,
                display_name=None,
                role="authenticated",
                litellm_key=None,
                letta_agent_id=None,
                agent_status=None,
                agents=[],
                created_at=None,
                last_active=None,
                metadata={"fallback": True, "ams_error": str(e)}
            )
        
        logger.info(
            "User profile data from AMS",
            user_id=user_id,
            profile_data=data,
            agents_data=data.get("agents", {})
        )
        
        # Convert AMS response to UserProfile model
        # AMS returns different structure, need to adapt
        agents_data = data.get("agents", {})
        agents_list = []
        
        # Convert agents dict to list of AgentSummary
        if isinstance(agents_data, dict):
            for agent_id, agent_info in agents_data.items():
                if isinstance(agent_info, dict):
                    agents_list.append(AgentSummary(
                        agent_id=agent_id,
                        name=agent_info.get("name", f"Agent {agent_id}"),
                        description=agent_info.get("description"),
                        status=agent_info.get("status", "unknown"),
                        model=agent_info.get("model"),
                        created_at=agent_info.get("created_at", data.get("created_at")),
                        updated_at=agent_info.get("updated_at", data.get("updated_at")),
                        message_count=agent_info.get("message_count")
                    ))
        
        # If there's a letta_agent_id, add it as an agent
        if data.get("letta_agent_id") and not agents_list:
            agents_list.append(AgentSummary(
                agent_id=data["letta_agent_id"],
                name=data.get("name", "Letta Agent"),
                description="Letta agent from AMS",
                status=data.get("agent_status", "unknown"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at")
            ))
        
        user_profile = UserProfile(
            user_id=data["id"],
            email=data.get("email"),
            display_name=data.get("name"),
            role="authenticated",  # Default role
            litellm_key=data.get("litellm_key"),
            letta_agent_id=data.get("letta_agent_id"),
            agent_status=data.get("agent_status"),
            agents=agents_list,
            created_at=data.get("created_at"),
            last_active=data.get("updated_at"),
            metadata={
                "profile_exists": data.get("profile_exists")
            }
        )
        
        # Cache the result for 5 seconds (very short TTL to ensure fresh data, only protects against burst requests)
        await cache_manager.set(cache_key, user_profile.model_dump(), ttl=5)
        
        return user_profile
    
    async def create_agent(
        self,
        user_id: str,
        request_data: CreateAgentRequest,
        idempotency_key: Optional[str] = None
    ) -> AgentInstance:
        """Create a new agent via AMS."""
        logger.info(
            "Creating agent via AMS",
            user_id=user_id,
            template_id=request_data.template_id,
            agent_name=request_data.agent_name,
            idempotency_key=idempotency_key
        )
        
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key  # AMS expects this header name
        
        # Prepare payload according to AMS Edge function expectations
        payload = {
            "template_id": request_data.template_id,
            "use_latest": request_data.use_latest
        }
        
        if request_data.version:
            payload["version"] = request_data.version
            payload["use_latest"] = False  # If version is specified, don't use latest
        
        if request_data.agent_name:
            payload["agent_name"] = request_data.agent_name
        
        if request_data.variables:
            payload["variables"] = request_data.variables
        
        response = await self._make_request(
            method="POST",
            path="/agents/create",  # Direct path to AMS endpoint
            user_id=user_id,
            headers=headers,
            json_data=payload
        )
        
        data = response.json()
        
        # Extract agent data from AMS response
        # AMS returns: {'agent': {...}, 'template_checksum': '...'}
        agent_data = data.get('agent', {})
        if not agent_data:
            raise ValueError("No agent data in AMS response")
        
        # Map AMS agent data to our AgentInstance format
        agent_instance_data = {
            'agent_id': agent_data.get('id'),
            'user_id': user_id,  # We know the user_id from the request
            'name': agent_data.get('name'),
            'description': agent_data.get('description'),
            'status': 'active',  # Default status for newly created agents
            'config': agent_data.get('config', {}),
            'memory_summary': agent_data.get('memory'),
            'statistics': {},
            'created_at': agent_data.get('created_at'),
            'updated_at': agent_data.get('last_updated'),
            'metadata': {
                'template_checksum': data.get('template_checksum'),
                'letta_agent_id': agent_data.get('id')
            }
        }
        
        # Invalidate user profile cache
        await self._invalidate_user_cache(user_id)
        
        return AgentInstance(**agent_instance_data)
    
    async def upgrade_agent(
        self,
        user_id: str,
        agent_id: str,
        request_data: UpgradeAgentRequest,
        idempotency_key: Optional[str] = None
    ) -> AgentInstance:
        """Upgrade an agent via AMS."""
        # First verify ownership
        await self._verify_agent_ownership(user_id, agent_id)
        
        logger.info(
            "Upgrading agent via AMS",
            user_id=user_id,
            agent_id=agent_id,
            target_version=request_data.target_version,
            idempotency_key=idempotency_key
        )
        
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key  # AMS expects this header name
        
        # Prepare payload according to AMS Edge function expectations
        payload = {
            "target_version": request_data.target_version,
            "use_latest": request_data.use_latest,
            "dry_run": request_data.dry_run,
            "use_queue": request_data.use_queue
        }
        
        response = await self._make_request(
            method="POST",
            path=f"/agents/{agent_id}/upgrade",  # Direct path to AMS endpoint
            user_id=user_id,
            headers=headers,
            json_data=payload
        )
        
        data = response.json()
        
        # Invalidate caches
        await self._invalidate_user_cache(user_id)
        await self._invalidate_agent_ownership_cache(agent_id)
        
        return AgentInstance(**data)
    
    async def validate_template(
        self,
        template_content: str,
        template_format: str = "yaml"
    ) -> Dict[str, Any]:
        """Validate template content via AMS."""
        logger.info(
            "Validating template via AMS",
            format=template_format,
            content_length=len(template_content)
        )
        
        response = await self._make_request(
            method="POST",
            path="/templates/validate",
            json_data={
                "template_content": template_content,
                "template_format": template_format,
                "strict_validation": True
            }
        )
        
        return response.json()
    
    async def publish_template(
        self,
        user_id: str,
        template_id: str,
        version: str,
        is_public: bool = False,
        changelog: Optional[str] = None,
        tags: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Publish template via AMS."""
        logger.info(
            "Publishing template via AMS",
            user_id=user_id,
            template_id=template_id,
            version=version,
            is_public=is_public,
            idempotency_key=idempotency_key
        )
        
        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        
        response = await self._make_request(
            method="POST",
            path="/templates/publish",
            user_id=user_id,
            headers=headers,
            json_data={
                "template_id": template_id,
                "version": version,
                "is_public": is_public,
                "changelog": changelog,
                "tags": tags or []
            }
        )
        
        return response.json()
    
    async def verify_agent_ownership(self, user_id: str, agent_id: str) -> bool:
        """Verify that user owns the specified agent."""
        try:
            # Get user profile to check if agent is in their agents list
            user_profile = await self.get_user_profile(user_id)
            
            # Check if the agent_id exists in the user's agents
            for agent in user_profile.agents:
                if agent.agent_id == agent_id:
                    return True
            
            return False
            
        except Exception:
            # If we can't verify ownership, assume not owned for security
            return False
    
    async def _verify_agent_ownership(self, user_id: str, agent_id: str):
        """Verify agent ownership and raise exception if not owned."""
        if not await self.verify_agent_ownership(user_id, agent_id):
            raise NotFoundError(
                f"Agent {agent_id} not found or not owned by user",
                context={"user_id": user_id, "agent_id": agent_id}
            )
    
    async def _invalidate_user_cache(self, user_id: str):
        """Invalidate user-related cache entries."""
        cache_keys = [
            f"user_profile:{user_id}",
            f"ams_user_profile:{user_id}",  # AMS-specific cache
            f"agent_ownership:*:{user_id}"  # Pattern for ownership cache
        ]
        
        for key in cache_keys:
            if "*" in key:
                # Clear pattern-based keys
                await cache_manager.clear_cache_pattern(key)
            else:
                await cache_manager.delete(key)
    
    async def _invalidate_agent_ownership_cache(self, agent_id: str):
        """Invalidate agent ownership cache."""
        # Clear all ownership entries for this agent
        await cache_manager.clear_cache_pattern(f"agent_ownership:{agent_id}:*")
    
    async def get_agent_details(self, user_id: str, agent_id: str) -> AgentInstance:
        """Get detailed agent information."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="GET",
            path=f"/agents/{agent_id}",
            user_id=user_id
        )
        
        data = response.json()
        return AgentInstance(**data)
    
    async def list_user_agents(self, user_id: str) -> List[AgentSummary]:
        """List all agents for a user."""
        response = await self._make_request(
            method="GET",
            path="/agents",
            user_id=user_id
        )
        
        data = response.json()
        return [AgentSummary(**agent) for agent in data.get("agents", [])]


# Global client instance
_ams_client: Optional[AMSClient] = None


async def get_ams_client() -> AMSClient:
    """Get or create AMS client instance."""
    global _ams_client
    
    if _ams_client is None:
        _ams_client = AMSClient()  # Use regular client for now
    
    return _ams_client


async def close_ams_client():
    """Close AMS client."""
    global _ams_client
    
    if _ams_client:
        await _ams_client.close()
        _ams_client = None
