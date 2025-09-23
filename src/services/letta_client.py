"""
Letta HTTP client with intelligent path rewriting and security filtering.
"""

import time
import re
from typing import Dict, List, Optional, Any, Set
import httpx
import structlog

from src.config.settings import get_settings
from src.models.requests import SendMessageRequest, UpdateMemoryRequest, ArchivalMemoryRequest
from src.models.responses import LettaAgent, LettaMessage
from src.utils.cache import cache_manager
from src.utils.metrics import metrics
from src.utils.exceptions import UpstreamError, RequestTimeoutError, NotFoundError, AuthorizationError
from src.middleware.circuit_breaker import circuit_breaker, CircuitBreakerConfig

logger = structlog.get_logger(__name__)

# Whitelist of allowed Letta operations
ALLOWED_OPERATIONS = {
    # Agent operations
    r"^GET /v1/agents$": "GET /v1/agents",
    r"^GET /v1/agents/([^/]+)$": "GET /v1/agents/{id}",
    
    # Message operations
    r"^GET /v1/agents/([^/]+)/messages$": "GET /v1/agents/{id}/messages",
    r"^POST /v1/agents/([^/]+)/messages$": "POST /v1/agents/{id}/messages",
    r"^POST /v1/agents/([^/]+)/messages/stream$": "POST /v1/agents/{id}/messages/stream",
    
    # Memory operations
    r"^GET /v1/agents/([^/]+)/memory$": "GET /v1/agents/{id}/memory",
    r"^PUT /v1/agents/([^/]+)/memory$": "PUT /v1/agents/{id}/memory",
    
    # Archival memory operations
    r"^GET /v1/agents/([^/]+)/archival$": "GET /v1/agents/{id}/archival",
    r"^POST /v1/agents/([^/]+)/archival$": "POST /v1/agents/{id}/archival",
}

# Blacklisted operations (security filtering)
BLACKLISTED_OPERATIONS = {
    r"^POST /v1/agents$",           # Agent creation (only via AMS)
    r"^PUT /v1/agents/([^/]+)$",    # Agent editing (only via AMS)
    r"^DELETE /v1/agents/([^/]+)$", # Agent deletion (only via AMS)
    r"^/admin/.*$",              # Admin functions
    r"^/users/.*$",              # User functions
}


class LettaClient:
    """HTTP client for Letta with path rewriting and security filtering."""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = str(self.settings.letta_base_url).rstrip('/')
        self.timeout = self.settings.letta_timeout
        self.api_key = self.settings.letta_api_key
        
        logger.info(
            "LettaClient initialized",
            base_url=self.base_url,
            timeout=self.timeout,
            api_key_present=bool(self.api_key)
        )
        
        # Configure HTTP client according to Letta API documentation
        # Letta uses API tokens in Authorization header
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": f"AI-Agent-Gateway/{self.settings.version}",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100
            )
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def health_check(self) -> dict:
        """
        Check Letta server health according to API documentation.
        GET /health endpoint as documented in https://docs.letta.com/api-reference/overview
        """
        try:
            response = await self.client.get("/health")
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "status_code": response.status_code,
                "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            }
        except Exception as e:
            logger.error("Letta health check failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _rewrite_path(self, original_path: str, method: str) -> Optional[str]:
        """
        Rewrite API Gateway path to Letta API path with security filtering.
        
        Args:
            original_path: Original path from API Gateway (e.g., /api/v1/letta/agents)
            method: HTTP method
            
        Returns:
            Rewritten Letta API path or None if blocked
        """
        # Remove /api/v1/letta prefix and add /v1/ prefix for Letta API
        if original_path.startswith("/api/v1/letta"):
            letta_path = original_path[13:]  # Remove /api/v1/letta
        else:
            letta_path = original_path
        
        # Ensure path starts with /
        if not letta_path.startswith("/"):
            letta_path = "/" + letta_path
            
        # Add /v1/ prefix for Letta API
        if not letta_path.startswith("/v1/"):
            letta_path = "/v1" + letta_path
        
        # Create full operation string for pattern matching
        operation = f"{method} {letta_path}"
        
        # Check blacklist first
        for pattern in BLACKLISTED_OPERATIONS:
            if re.match(pattern, letta_path):
                logger.warning(
                    "Blocked blacklisted Letta operation",
                    operation=operation,
                    pattern=pattern
                )
                return None
        
        # Check whitelist
        for pattern, description in ALLOWED_OPERATIONS.items():
            if re.match(pattern, operation):
                logger.debug(
                    "Allowed Letta operation",
                    operation=operation,
                    pattern=pattern,
                    description=description
                )
                return letta_path
        
        # Not in whitelist
        logger.warning(
            "Blocked non-whitelisted Letta operation",
            operation=operation
        )
        return None
    
    def _filter_response_data(self, data: Any) -> Any:
        """Filter response data to hide internal fields."""
        if isinstance(data, dict):
            # Remove internal fields
            filtered_data = data.copy()
            internal_fields = {
                "_internal_id",
                "_system_config",
                "_private_metadata",
                "api_key",
                "secret",
                "password"
            }
            
            for field in internal_fields:
                filtered_data.pop(field, None)
            
            # Recursively filter nested objects
            for key, value in filtered_data.items():
                filtered_data[key] = self._filter_response_data(value)
            
            return filtered_data
        
        elif isinstance(data, list):
            return [self._filter_response_data(item) for item in data]
        
        else:
            return data
    
    async def _make_request(
        self,
        method: str,
        path: str,
        user_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        """Make HTTP request to Letta with error handling and metrics."""
        start_time = time.time()
        
        # Security check: rewrite and validate path
        letta_path = self._rewrite_path(path, method)
        if letta_path is None:
            raise AuthorizationError(
                f"Operation not allowed: {method} {path}",
                context={"method": method, "path": path}
            )
        
        # Prepare headers
        # Add user context headers if user_id provided
        # Note: Letta uses API tokens for authentication, not user IDs
        # The user_id is used for filtering/context, not authentication
        request_headers = {}
        if user_id:
            # Letta may use X-User-Id for context, but authentication is via API token
            request_headers["X-User-Id"] = user_id
        if headers:
            request_headers.update(headers)
        
        try:
            logger.info(
                "Making request to Letta",
                method=method,
                url=letta_path,
                headers=request_headers,
                json_data=json_data,
                user_id=user_id,
                full_url=f"{self.base_url}{letta_path}"
            )
            
            response = await self.client.request(
                method=method,
                url=letta_path,
                headers=request_headers,
                json=json_data,
                params=params
            )
            
            duration = time.time() - start_time
            
            # Record metrics
            metrics.record_upstream_request("letta", response.status_code, duration)
            
            # Log request
            logger.debug(
                "Letta request completed",
                method=method,
                original_path=path,
                letta_path=letta_path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2)
            )
            
            # Log response details for debugging
            if response.status_code >= 400:
                try:
                    response_text = response.text
                    logger.warning(
                        "Letta error response",
                        status_code=response.status_code,
                        response_text=response_text,
                        url=letta_path,
                        method=method
                    )
                except Exception:
                    logger.warning(
                        "Letta error response (could not read text)",
                        status_code=response.status_code,
                        url=letta_path,
                        method=method
                    )
            
            # Handle error status codes
            if response.status_code >= 400:
                error_detail = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                if response.status_code == 404:
                    raise NotFoundError(
                        f"Letta resource not found: {letta_path}",
                        context={"status_code": response.status_code, "detail": error_detail}
                    )
                else:
                    raise UpstreamError(
                        f"Letta request failed: {response.status_code}",
                        service_name="letta",
                        upstream_status=response.status_code,
                        context={"detail": error_detail}
                    )
            
            return response
            
        except httpx.TimeoutException:
            duration = time.time() - start_time
            metrics.record_upstream_request("letta", 408, duration)
            
            raise RequestTimeoutError(
                "Letta request timeout",
                timeout_seconds=self.timeout,
                context={"method": method, "path": letta_path}
            )
        
        except httpx.RequestError as e:
            duration = time.time() - start_time
            metrics.record_upstream_request("letta", 502, duration)
            
            raise UpstreamError(
                f"Letta connection error: {str(e)}",
                service_name="letta",
                context={"method": method, "path": letta_path, "error": str(e)}
            )
    
    async def proxy_request(
        self,
        method: str,
        path: str,
        user_id: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Proxy request to Letta with path rewriting and security filtering.
        This is the main method for the unified Letta proxy.
        """
        # Verify agent ownership for agent-specific endpoints
        agent_id = self._extract_agent_id_from_path(path)
        if agent_id:
            await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method=method,
            path=path,
            user_id=user_id,
            headers=headers,
            json_data=json_data,
            params=params
        )
        
        # Get response data
        if response.headers.get("content-type", "").startswith("application/json"):
            data = response.json()
            # Filter internal fields
            filtered_data = self._filter_response_data(data)
            return {
                "status_code": response.status_code,
                "data": filtered_data,
                "headers": dict(response.headers)
            }
        else:
            return {
                "status_code": response.status_code,
                "data": response.text,
                "headers": dict(response.headers)
            }
    
    def _extract_agent_id_from_path(self, path: str) -> Optional[str]:
        """Extract agent ID from path for ownership verification."""
        # Remove /api/v1/letta prefix if present
        if path.startswith("/api/v1/letta"):
            path = path[13:]
        
        # Look for agent ID pattern
        agent_match = re.search(r"/agents/([^/]+)", path)
        if agent_match:
            return agent_match.group(1)
        
        return None
    
    async def _verify_agent_ownership(self, user_id: str, agent_id: str):
        """Verify that user owns the agent (via AMS)."""
        from src.services.ams_client import get_ams_client
        
        ams_client = await get_ams_client()
        if not await ams_client.verify_agent_ownership(user_id, agent_id):
            raise NotFoundError(
                f"Agent {agent_id} not found or not owned by user",
                context={"user_id": user_id, "agent_id": agent_id}
            )
    
    async def list_agents(self, user_id: str) -> List[LettaAgent]:
        """List all Letta agents for user."""
        response = await self._make_request(
            method="GET",
            path="/api/v1/letta/agents",
            user_id=user_id
        )
        
        data = response.json()
        
        # Filter agents by ownership (additional security layer)
        from src.services.ams_client import get_ams_client
        ams_client = await get_ams_client()
        
        owned_agents = []
        for agent_data in data.get("agents", []):
            agent_id = agent_data.get("id")
            if agent_id and await ams_client.verify_agent_ownership(user_id, agent_id):
                owned_agents.append(LettaAgent(**agent_data))
        
        return owned_agents
    
    async def get_agent(self, user_id: str, agent_id: str) -> LettaAgent:
        """Get specific Letta agent."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="GET",
            path=f"/api/v1/letta/agents/{agent_id}",
            user_id=user_id
        )
        
        data = response.json()
        return LettaAgent(**data)
    
    async def send_message(
        self,
        user_id: str,
        agent_id: str,
        message_request: SendMessageRequest
    ) -> Dict[str, Any]:
        """Send message to Letta agent."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="POST",
            path=f"/api/v1/letta/agents/{agent_id}/messages",
            user_id=user_id,
            json_data=message_request.dict(exclude_none=True)
        )
        
        return response.json()
    
    async def get_messages(
        self,
        user_id: str,
        agent_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[LettaMessage]:
        """Get agent messages."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        
        response = await self._make_request(
            method="GET",
            path=f"/api/v1/letta/agents/{agent_id}/messages",
            user_id=user_id,
            params=params
        )
        
        data = response.json()
        return [LettaMessage(**msg) for msg in data.get("messages", [])]
    
    async def get_memory(self, user_id: str, agent_id: str) -> Dict[str, Any]:
        """Get agent memory."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="GET",
            path=f"/api/v1/letta/agents/{agent_id}/memory",
            user_id=user_id
        )
        
        return response.json()
    
    async def update_memory(
        self,
        user_id: str,
        agent_id: str,
        memory_request: UpdateMemoryRequest
    ) -> Dict[str, Any]:
        """Update agent memory."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="PUT",
            path=f"/api/v1/letta/agents/{agent_id}/memory",
            user_id=user_id,
            json_data=memory_request.dict(exclude_none=True)
        )
        
        return response.json()
    
    async def get_archival_memory(
        self,
        user_id: str,
        agent_id: str,
        query: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get agent archival memory."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        params = {}
        if query:
            params["query"] = query
        if limit is not None:
            params["limit"] = limit
        
        response = await self._make_request(
            method="GET",
            path=f"/api/v1/letta/agents/{agent_id}/archival",
            user_id=user_id,
            params=params
        )
        
        return response.json()
    
    async def add_archival_memory(
        self,
        user_id: str,
        agent_id: str,
        archival_request: ArchivalMemoryRequest
    ) -> Dict[str, Any]:
        """Add to agent archival memory."""
        await self._verify_agent_ownership(user_id, agent_id)
        
        response = await self._make_request(
            method="POST",
            path=f"/api/v1/letta/agents/{agent_id}/archival",
            user_id=user_id,
            json_data=archival_request.dict(exclude_none=True)
        )
        
        return response.json()


# Global client instance
_letta_client: Optional[LettaClient] = None


async def get_letta_client() -> LettaClient:
    """Get or create Letta client instance."""
    global _letta_client
    
    if _letta_client is None:
        _letta_client = LettaClient()  # Use regular client for now
    
    return _letta_client


async def close_letta_client():
    """Close Letta client."""
    global _letta_client
    
    if _letta_client:
        await _letta_client.close()
        _letta_client = None
