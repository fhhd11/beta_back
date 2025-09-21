#!/usr/bin/env python3
"""
Simple test script to verify basic functionality.
"""

import os
import sys

# Add src to path
sys.path.insert(0, 'src')

# Set minimal environment variables
os.environ['ENVIRONMENT'] = 'development'
os.environ['DEBUG'] = 'true'
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['AMS_BASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co/functions/v1/ams'
os.environ['LETTA_BASE_URL'] = 'https://lettalettalatest-production-a3ba.up.railway.app'
os.environ['LITELLM_BASE_URL'] = 'https://litellm-production-1c8b.up.railway.app'
os.environ['SUPABASE_URL'] = 'https://ptcpemfokwjgpjgmbgoj.supabase.co'
os.environ['SUPABASE_JWT_SECRET'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB0Y3BlbWZva3dqZ3BqZ21iZ29qIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NjI0MDUzMSwiZXhwIjoyMDcxODE2NTMxfQ.02O9W9_phruZRvCx55Tkh6EFG2GLPl3Eo7qdFAlX0Os'
os.environ['LETTA_API_KEY'] = 'letta-dev-key'
os.environ['AGENT_SECRET_MASTER_KEY'] = 'dev-agent-secret'
os.environ['ENABLE_RATE_LIMITING'] = 'false'
os.environ['ENABLE_CACHING'] = 'false'
os.environ['ENABLE_METRICS'] = 'true'
os.environ['ENABLE_DOCS'] = 'true'
os.environ['ALLOWED_ORIGINS'] = '["*"]'

try:
    print("=== Testing configuration loading ===")
    from src.config.settings import get_settings
    
    settings = get_settings()
    print(f"✅ Settings loaded successfully!")
    print(f"   Environment: {settings.environment}")
    print(f"   Debug: {settings.debug}")
    print(f"   AMS URL: {settings.ams_base_url}")
    print(f"   Supabase URL: {settings.supabase_url}")
    print(f"   Allowed Origins: {settings.allowed_origins}")
    print()
    
    print("=== Testing FastAPI app creation ===")
    from src.main import app
    print(f"✅ FastAPI app created successfully!")
    print(f"   App title: {app.title}")
    print(f"   App version: {app.version}")
    print()
    
    print("=== All basic tests passed! ===")
    print("🎉 The API Gateway configuration is working correctly!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
