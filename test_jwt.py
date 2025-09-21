#!/usr/bin/env python3
"""
Test JWT token decoding to find the correct secret.
"""

import base64
import json

# JWT tokens provided
anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB0Y3BlbWZva3dqZ3BqZ21iZ29qIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNDA1MzEsImV4cCI6MjA3MTgxNjUzMX0.YpHcYonTongwW_U6Ya5pphoejGIx_se_2XEIvmFZywI"
service_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB0Y3BlbWZva3dqZ3BqZ21iZ29qIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NjI0MDUzMSwiZXhwIjoyMDcxODE2NTMxfQ.02O9W9_phruZRvCx55Tkh6EFG2GLPl3Eo7qdFAlX0Os"

def decode_jwt_payload(token):
    """Decode JWT payload without verification."""
    try:
        # Split token
        parts = token.split('.')
        if len(parts) != 3:
            return None
            
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        print(f"Error decoding: {e}")
        return None

print("=== JWT Token Analysis ===")
print()

print("ANON KEY:")
anon_payload = decode_jwt_payload(anon_key)
if anon_payload:
    print(json.dumps(anon_payload, indent=2))
print()

print("SERVICE KEY:")
service_payload = decode_jwt_payload(service_key)
if service_payload:
    print(json.dumps(service_payload, indent=2))
print()

# For Supabase, the JWT secret is typically the same for both tokens
# and can be found in Supabase project settings
print("=== Configuration Notes ===")
print("1. Both tokens are from the same Supabase project: ptcpemfokwjgpjgmbgoj")
print("2. JWT secret should be obtained from Supabase project settings")
print("3. For development, we can use a placeholder and test connectivity")
print()

print("=== Recommended Configuration ===")
print("SUPABASE_URL=https://ptcpemfokwjgpjgmbgoj.supabase.co")
print("SUPABASE_JWT_SECRET=<get-from-supabase-project-settings>")
print("# For testing, we'll use a development secret")
