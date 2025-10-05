"""
Tests for system health endpoints.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert "services" in data
    assert "overall_status" in data
    assert "version" in data


def test_ping_endpoint(client: TestClient):
    """Test the simple ping endpoint."""
    response = client.get("/ping")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_api_info_endpoint(client: TestClient):
    """Test the API information endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert data["name"] == "AI Agent Platform API Gateway"
    assert "version" in data
    assert "endpoints" in data
    assert len(data["endpoints"]) > 0


def test_metrics_endpoint(client: TestClient):
    """Test the Prometheus metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    
    # Check for some expected metrics
    content = response.text
    assert "api_requests_total" in content
    assert "api_request_duration_seconds" in content


def test_detailed_status_endpoint(client: TestClient):
    """Test the detailed status endpoint."""
    response = client.get("/status")
    assert response.status_code == 200
    
    data = response.json()
    assert "overall_status" in data
    assert "services" in data
    assert "features" in data
    assert "metrics" in data
    
    # Check features configuration
    features = data["features"]
    assert "rate_limiting" in features
    assert "caching" in features
    assert "metrics" in features
