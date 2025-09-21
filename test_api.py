#!/usr/bin/env python3
"""
API Testing Script for AI Agent Platform API Gateway
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_endpoint(method, path, description, headers=None, json_data=None):
    """Test a single API endpoint."""
    url = f"{BASE_URL}{path}"
    print(f"\n🔍 Testing: {description}")
    print(f"   {method} {path}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            print(f"   ❌ Unsupported method: {method}")
            return
        
        print(f"   Status: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"   Response: {response.text[:200]}...")
        else:
            print(f"   Response: {response.text[:200]}...")
        
        if 200 <= response.status_code < 300:
            print("   ✅ Success")
        else:
            print("   ⚠️ Non-2xx status")
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error: {e}")

def main():
    print("🚀 AI Agent Platform API Gateway - API Testing")
    print("=" * 60)
    
    # Test basic endpoints
    test_endpoint("GET", "/ping", "Simple ping check")
    test_endpoint("GET", "/", "API information")
    test_endpoint("GET", "/health", "Health check")
    test_endpoint("GET", "/metrics", "Prometheus metrics")
    
    # Test documentation endpoints
    test_endpoint("GET", "/docs", "Swagger UI documentation")
    test_endpoint("GET", "/openapi.json", "OpenAPI schema")
    
    # Test protected endpoints (should return 401)
    test_endpoint("GET", "/api/v1/me", "User profile (no auth - should fail)")
    test_endpoint("GET", "/api/v1/agents", "List agents (no auth - should fail)")
    
    # Test with mock JWT token
    mock_headers = {
        "Authorization": "Bearer mock-jwt-token"
    }
    test_endpoint("GET", "/api/v1/me", "User profile (mock auth - should fail)", headers=mock_headers)
    
    print("\n" + "=" * 60)
    print("🏁 API Testing completed!")
    print("\nNote: Some endpoints are expected to fail without proper authentication.")
    print("This is normal behavior for a secure API Gateway.")

if __name__ == "__main__":
    main()
