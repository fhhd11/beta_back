"""
Pytest configuration and fixtures for API Gateway tests.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
import pytest_asyncio

from src.main import app
from src.config.settings import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def async_client():
    """Create an async test client for the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def settings():
    """Get application settings for tests."""
    return get_settings()


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for testing authentication."""
    return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXItaWQiLCJlbWFpbCI6InRlc3RAdGVzdC5jb20iLCJyb2xlIjoidXNlciIsImlhdCI6MTYzMjQ2MjQwMCwiZXhwIjoyNTMyNDYyNDAwfQ.test-signature"


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Authentication headers with mock JWT token."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}


@pytest.fixture
def agent_secret_headers():
    """Agent secret authentication headers."""
    return {"Authorization": "Bearer test-agent-secret-key"}
