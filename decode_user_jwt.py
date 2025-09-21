#!/usr/bin/env python3
"""
Decode the provided user JWT token to understand its structure.
"""

import base64
import json

# User JWT token provided
user_token = "eyJhbGciOiJIUzI1NiIsImtpZCI6InBCMHFmdEVVVHFuRkxoaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3B0Y3BlbWZva3dqZ3BqZ21iZ29qLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0ZjRjNGE0My02MWI5LTQ4OGUtODJiNi1jMDY3OGE0NjBlNzEiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU4NDI5NTA5LCJpYXQiOjE3NTg0MjU5MDksImVtYWlsIjoidGVzdDExQHVzZXIuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NTg0MjU5MDl9XSwic2Vzc2lvbl9pZCI6IjE5N2Y5ZWJkLTNlZjUtNGM1ZC04Y2FiLTQxZjRlOWY5NmJkYiIsImlzX2Fub255bW91cyI6ZmFsc2V9.fG5sQEMcVxxR38uRp5MTlDpuewXJVwY3MQsSbY7y1lI"

def decode_jwt_payload(token):
    """Decode JWT payload without verification."""
    try:
        # Split token
        parts = token.split('.')
        if len(parts) != 3:
            return None
            
        # Decode header
        header = parts[0]
        header += '=' * (4 - len(header) % 4)
        decoded_header = base64.urlsafe_b64decode(header)
        
        # Decode payload
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded_payload = base64.urlsafe_b64decode(payload)
        
        return {
            "header": json.loads(decoded_header),
            "payload": json.loads(decoded_payload),
            "signature": parts[2]
        }
    except Exception as e:
        print(f"Error decoding: {e}")
        return None

print("=== USER JWT TOKEN ANALYSIS ===")
print()

token_data = decode_jwt_payload(user_token)
if token_data:
    print("HEADER:")
    print(json.dumps(token_data["header"], indent=2))
    print()
    
    print("PAYLOAD:")
    print(json.dumps(token_data["payload"], indent=2))
    print()
    
    print("=== KEY INFORMATION ===")
    payload = token_data["payload"]
    print(f"User ID: {payload.get('sub')}")
    print(f"Email: {payload.get('email')}")
    print(f"Role: {payload.get('role')}")
    print(f"Issuer: {payload.get('iss')}")
    print(f"Audience: {payload.get('aud')}")
    print(f"Expires: {payload.get('exp')} (timestamp)")
    
    # Convert timestamp to readable date
    import datetime
    exp_time = datetime.datetime.fromtimestamp(payload.get('exp', 0))
    iat_time = datetime.datetime.fromtimestamp(payload.get('iat', 0))
    print(f"Issued at: {iat_time}")
    print(f"Expires at: {exp_time}")
    print(f"Valid for: {exp_time - iat_time}")
    
    print()
    print("=== TESTING NOTES ===")
    print("1. This is a real Supabase JWT token")
    print("2. User ID: 4f4c4a43-61b9-488e-82b6-c0678a460e71")
    print("3. Email: test11@user.com")
    print("4. Role: authenticated")
    print("5. Token is valid until:", exp_time)
    
    if exp_time > datetime.datetime.now():
        print("6. ✅ Token is currently VALID")
    else:
        print("6. ❌ Token is EXPIRED")
        
else:
    print("Failed to decode token")
