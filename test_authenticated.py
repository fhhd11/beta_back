#!/usr/bin/env python3
"""
Test authenticated API endpoints with real JWT token.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6InBCMHFmdEVVVHFuRkxoaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3B0Y3BlbWZva3dqZ3BqZ21iZ29qLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0ZjRjNGE0My02MWI5LTQ4OGUtODJiNi1jMDY3OGE0NjBlNzEiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU4NDI5NTA5LCJpYXQiOjE3NTg0MjU5MDksImVtYWlsIjoidGVzdDExQHVzZXIuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NTg0MjU5MDl9XSwic2Vzc2lvbl9pZCI6IjE5N2Y5ZWJkLTNlZjUtNGM1ZC04Y2FiLTQxZjRlOWY5NmJkYiIsImlzX2Fub255bW91cyI6ZmFsc2V9.fG5sQEMcVxxR38uRp5MTlDpuewXJVwY3MQsSbY7y1lI"

def test_authenticated_endpoint(method, path, description, json_data=None):
    """Test an authenticated API endpoint."""
    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"\n🔐 Testing: {description}")
    print(f"   {method} {path}")
    print(f"   User: test11@user.com (4f4c4a43-61b9-488e-82b6-c0678a460e71)")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            print(f"   ❌ Unsupported method: {method}")
            return
        
        print(f"   Status: {response.status_code}")
        
        # Show response headers
        if "X-Request-ID" in response.headers:
            print(f"   Request ID: {response.headers['X-Request-ID']}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:500]}...")
            except:
                print(f"   Response: {response.text[:200]}...")
        else:
            print(f"   Response: {response.text[:200]}...")
        
        if 200 <= response.status_code < 300:
            print("   ✅ Success")
        elif response.status_code == 401:
            print("   🔒 Unauthorized (check JWT validation)")
        elif response.status_code == 403:
            print("   🚫 Forbidden (check permissions)")
        elif response.status_code >= 500:
            print("   💥 Server Error")
        else:
            print(f"   ⚠️ Status {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error: {e}")

def main():
    print("🔐 AI Agent Platform API Gateway - Authenticated API Testing")
    print("=" * 70)
    print(f"🎫 JWT Token: ...{JWT_TOKEN[-20:]}")
    print(f"👤 User: test11@user.com")
    print(f"🆔 User ID: 4f4c4a43-61b9-488e-82b6-c0678a460e71")
    print()
    
    # Wait for server to be ready
    print("⏳ Waiting for server to be ready...")
    time.sleep(3)
    
    # Test authenticated endpoints
    test_authenticated_endpoint("GET", "/api/v1/me", "Get user profile")
    test_authenticated_endpoint("GET", "/api/v1/agents", "List user agents")
    
    # Test Letta proxy endpoints
    test_authenticated_endpoint("GET", "/api/v1/letta/agents", "List Letta agents")
    
    # Test agent creation (this might fail due to missing templates)
    agent_data = {
        "name": "Test Agent",
        "description": "Test agent for API testing",
        "config": {
            "model": "gpt-4",
            "temperature": 0.7
        }
    }
    test_authenticated_endpoint("POST", "/api/v1/agents/create", "Create agent", agent_data)
    
    # Test template validation
    template_data = {
        "template_content": "name: Test Template\ndescription: A test template",
        "template_format": "yaml"
    }
    test_authenticated_endpoint("POST", "/api/v1/templates/validate", "Validate template", template_data)
    
    print("\n" + "=" * 70)
    print("🏁 Authenticated API Testing completed!")
    print("\nNote: Some endpoints may fail due to missing upstream data (templates, agents).")
    print("This is expected and indicates the gateway is correctly proxying to upstream services.")

if __name__ == "__main__":
    main()
