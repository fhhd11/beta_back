#!/usr/bin/env python3
"""
Create a simple test endpoint to verify authentication works.
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Set environment
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

sys.path.insert(0, 'src')

from jose import jwt
from jose.exceptions import JWTError

app = FastAPI(title="Simple Auth Test")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = 'o5MX3zaq8N9w6Dk3HxRacT8eZDmr3zeTT3Yf+AEx1QS5wQ2+4B8QSclUrdbnKcYPntrzHla/R9GvGMpKdw2qlA=='

def get_current_user(request: Request):
    """Extract and validate JWT token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = auth_header[7:]  # Remove "Bearer "
    
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": False
            }
        )
        
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "role": payload.get("role")
        }
        
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Simple auth test server", "status": "running"}

@app.get("/test-auth")
async def test_auth(request: Request, user = Depends(get_current_user)):
    return {
        "message": "Authentication successful!",
        "user": user,
        "timestamp": "2025-09-21T03:48:00Z"
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting simple auth test server on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
