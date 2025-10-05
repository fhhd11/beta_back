"""
Tests for authentication middleware.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


def test_public_endpoints_no_auth(client: TestClient):
    """Test that public endpoints don't require authentication."""
    public_endpoints = ["/", "/health", "/ping", "/docs", "/openapi.json"]
    
    for endpoint in public_endpoints:
        response = client.get(endpoint)
        # Should not return 401 (unauthorized)
        assert response.status_code != 401


def test_protected_endpoints_require_auth(client: TestClient):
    """Test that protected endpoints require authentication."""
    protected_endpoints = [
        "/api/v1/me",
        "/api/v1/agents",
        "/api/v1/letta/agents"
    ]
    
    for endpoint in protected_endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401
        
        data = response.json()
        assert data["error"]["code"] == "AUTHENTICATION_ERROR"


def test_invalid_jwt_token(client: TestClient):
    """Test authentication with invalid JWT token."""
    headers = {"Authorization": "Bearer invalid-token"}
    
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    
    data = response.json()
    assert data["error"]["code"] == "AUTHENTICATION_ERROR"


def test_missing_authorization_header(client: TestClient):
    """Test authentication without Authorization header."""
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    
    data = response.json()
    assert data["error"]["code"] == "AUTHENTICATION_ERROR"
    assert "Missing authentication token" in data["error"]["message"]


def test_malformed_authorization_header(client: TestClient):
    """Test authentication with malformed Authorization header."""
    headers = {"Authorization": "InvalidFormat token"}
    
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401


@patch('src.middleware.auth.jwt.decode')
def test_valid_jwt_token(mock_jwt_decode, client: TestClient):
    """Test authentication with valid JWT token."""
    # Mock JWT decode to return valid payload
    mock_jwt_decode.return_value = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "role": "user",
        "user_metadata": {},
        "app_metadata": {}
    }
    
    headers = {"Authorization": "Bearer valid-jwt-token"}
    
    # This will still fail because we don't have upstream services
    # but it should pass authentication
    response = client.get("/api/v1/me", headers=headers)
    
    # Should not be 401 (authentication error)
    assert response.status_code != 401
    
    # Verify JWT decode was called
    mock_jwt_decode.assert_called_once()
