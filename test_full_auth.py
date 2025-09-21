#!/usr/bin/env python3
"""
Full authentication test - create a request and test middleware directly.
"""

import os
import sys
import asyncio
sys.path.insert(0, 'src')

# Set environment variables
os.environ['ENVIRONMENT'] = 'development'
os.environ['SUPABASE_JWT_SECRET'] = 'o5MX3zaq8N9w6Dk3HxRacT8eZDmr3zeTT3Yf+AEx1QS5wQ2+4B8QSclUrdbnKcYPntrzHla/R9GvGMpKdw2qlA=='
os.environ['AMS_BASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co/functions/v1/ams'
os.environ['LETTA_BASE_URL'] = 'https://lettalettalatest-production-a3ba.up.railway.app'
os.environ['LITELLM_BASE_URL'] = 'https://litellm-production-1c8b.up.railway.app'
os.environ['SUPABASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co'
os.environ['LETTA_API_KEY'] = 'test'
os.environ['AGENT_SECRET_MASTER_KEY'] = 'test'
os.environ['ENABLE_CACHING'] = 'false'
os.environ['ALLOWED_ORIGINS'] = '["*"]'

JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6InBCMHFmdEVVVHFuRkxoaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3B0Y3BlbWZva3dqZ3BqZ21iZ29qLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0ZjRjNGE0My02MWI5LTQ4OGUtODJiNi1jMDY3OGE0NjBlNzEiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU4NDI5NTA5LCJpYXQiOjE3NTg0MjU5MDksImVtYWlsIjoidGVzdDExQHVzZXIuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NTg0MjU5MDl9XSwic2Vzc2lvbl9pZCI6IjE5N2Y5ZWJkLTNlZjUtNGM1ZC04Y2FiLTQxZjRlOWY5NmJkYiIsImlzX2Fub255bW91cyI6ZmFsc2V9.fG5sQEMcVxxR38uRp5MTlDpuewXJVwY3MQsSbY7y1lI"

async def test_auth():
    print("=== Full Authentication Test ===")
    
    # Import middleware
    from src.middleware.auth import AuthMiddleware, get_current_user
    from src.config.settings import get_settings
    
    settings = get_settings()
    auth_middleware = AuthMiddleware(None, settings)
    
    # Create mock request
    class MockRequest:
        def __init__(self, token):
            self.headers = {"Authorization": f"Bearer {token}"}
            self.url = type('MockURL', (), {'path': '/api/v1/me'})()
            self.state = type('MockState', (), {})()
        
        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
    
    class MockResponse:
        def __init__(self):
            self.status_code = 200
    
    # Test authentication
    mock_request = MockRequest(JWT_TOKEN)
    
    try:
        # Test JWT authentication directly
        user_context = await auth_middleware._validate_jwt_token(JWT_TOKEN)
        print("✅ JWT validation successful!")
        print(f"   User ID: {user_context.user_id}")
        print(f"   Email: {user_context.email}")
        print()
        
        # Test get_current_user function
        mock_request.state.user = user_context
        current_user = get_current_user(mock_request)
        print("✅ get_current_user successful!")
        print(f"   Current user: {current_user.email}")
        
    except Exception as e:
        print(f"❌ Authentication test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_auth())
