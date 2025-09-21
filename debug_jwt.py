#!/usr/bin/env python3
"""
Debug JWT validation to understand why authentication is failing.
"""

import os
import sys
sys.path.insert(0, 'src')

# Set environment variables
os.environ['ENVIRONMENT'] = 'development'
os.environ['DEBUG'] = 'true'
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['AMS_BASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co/functions/v1/ams'
os.environ['LETTA_BASE_URL'] = 'https://lettalettalatest-production-a3ba.up.railway.app'
os.environ['LITELLM_BASE_URL'] = 'https://litellm-production-1c8b.up.railway.app'
os.environ['SUPABASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co'
os.environ['SUPABASE_JWT_SECRET'] = 'o5MX3zaq8N9w6Dk3HxRacT8eZDmr3zeTT3Yf+AEx1QS5wQ2+4B8QSclUrdbnKcYPntrzHla/R9GvGMpKdw2qlA=='
os.environ['LETTA_API_KEY'] = 'letta-dev-key'
os.environ['AGENT_SECRET_MASTER_KEY'] = 'dev-agent-secret'
os.environ['ENABLE_RATE_LIMITING'] = 'false'
os.environ['ENABLE_CACHING'] = 'false'
os.environ['ENABLE_METRICS'] = 'true'
os.environ['ENABLE_DOCS'] = 'true'
os.environ['ALLOWED_ORIGINS'] = '["*"]'

# JWT token to test
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6InBCMHFmdEVVVHFuRkxoaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3B0Y3BlbWZva3dqZ3BqZ21iZ29qLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0ZjRjNGE0My02MWI5LTQ4OGUtODJiNi1jMDY3OGE0NjBlNzEiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU4NDI5NTA5LCJpYXQiOjE3NTg0MjU5MDksImVtYWlsIjoidGVzdDExQHVzZXIuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NTg0MjU5MDl9XSwic2Vzc2lvbl9pZCI6IjE5N2Y5ZWJkLTNlZjUtNGM1ZC04Y2FiLTQxZjRlOWY5NmJkYiIsImlzX2Fub255bW91cyI6ZmFsc2V9.fG5sQEMcVxxR38uRp5MTlDpuewXJVwY3MQsSbY7y1lI"

try:
    print("=== JWT Validation Debug ===")
    
    # Import JWT library
    from jose import jwt
    from jose.exceptions import JWTError, ExpiredSignatureError
    
    # Get settings
    from src.config.settings import get_settings
    settings = get_settings()
    
    print(f"JWT Secret (first 20 chars): {settings.supabase_jwt_secret[:20]}...")
    print(f"JWT Algorithm: {settings.jwt_algorithm}")
    print(f"JWT Audience: {settings.jwt_audience}")
    print(f"JWT Issuer: {settings.jwt_issuer}")
    print()
    
    # Try to decode the token
    print("🔍 Attempting to decode JWT token...")
    
    try:
        payload = jwt.decode(
            JWT_TOKEN,
            settings.supabase_jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": settings.jwt_audience is not None,
                "verify_iss": settings.jwt_issuer is not None
            }
        )
        
        print("✅ JWT validation SUCCESS!")
        print("Decoded payload:")
        print(f"  User ID: {payload.get('sub')}")
        print(f"  Email: {payload.get('email')}")
        print(f"  Role: {payload.get('role')}")
        print(f"  Issuer: {payload.get('iss')}")
        print(f"  Audience: {payload.get('aud')}")
        print()
        
        # Test UserContext creation
        from src.models.common import UserContext
        
        user_context = UserContext(
            user_id=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role", "authenticated"),
            metadata={**payload.get("user_metadata", {}), **payload.get("app_metadata", {})}
        )
        
        print("✅ UserContext creation SUCCESS!")
        print(f"  UserContext: {user_context}")
        
    except ExpiredSignatureError:
        print("❌ JWT validation FAILED: Token has expired")
        
    except JWTError as e:
        print(f"❌ JWT validation FAILED: {str(e)}")
        
        # Try without audience/issuer verification
        print("\n🔍 Trying without audience/issuer verification...")
        try:
            payload = jwt.decode(
                JWT_TOKEN,
                settings.supabase_jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": False,
                    "verify_iss": False
                }
            )
            print("✅ JWT validation SUCCESS (without aud/iss check)!")
            print(f"  Actual issuer: {payload.get('iss')}")
            print(f"  Actual audience: {payload.get('aud')}")
            
        except Exception as e2:
            print(f"❌ Still failed: {str(e2)}")
    
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"❌ Setup error: {e}")
    import traceback
    traceback.print_exc()
