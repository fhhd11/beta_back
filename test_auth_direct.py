#!/usr/bin/env python3
"""
Test JWT authentication directly bypassing middleware.
"""

import os
import sys
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

try:
    print("=== Direct JWT Authentication Test ===")
    
    # Import auth middleware
    from src.middleware.auth import AuthMiddleware
    from src.config.settings import get_settings
    
    settings = get_settings()
    auth_middleware = AuthMiddleware(None, settings)
    
    print(f"✅ AuthMiddleware created")
    print(f"   JWT Secret: {auth_middleware.jwt_secret[:20]}...")
    print(f"   Algorithm: {auth_middleware.jwt_algorithm}")
    print(f"   Audience: {auth_middleware.jwt_audience}")
    print()
    
    # Test token extraction
    class MockRequest:
        def __init__(self, token):
            self.headers = {"Authorization": f"Bearer {token}"}
    
    mock_request = MockRequest(JWT_TOKEN)
    extracted_token = auth_middleware._extract_jwt_token(mock_request)
    
    print(f"✅ Token extracted: {extracted_token[:20]}...")
    print()
    
    # Test token validation
    print("🔍 Testing JWT validation...")
    
    import asyncio
    async def test_validation():
        try:
            user_context = await auth_middleware._validate_jwt_token(JWT_TOKEN)
            print("✅ JWT validation SUCCESS!")
            print(f"   User ID: {user_context.user_id}")
            print(f"   Email: {user_context.email}")
            print(f"   Role: {user_context.role}")
            return True
        except Exception as e:
            print(f"❌ JWT validation FAILED: {e}")
            return False
    
    # Run the async test
    success = asyncio.run(test_validation())
    
    if success:
        print("\n🎉 Authentication should work! The issue might be elsewhere.")
    else:
        print("\n💥 Authentication is definitely broken.")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
