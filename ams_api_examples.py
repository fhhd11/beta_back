#!/usr/bin/env python3
"""
Примеры использования нового AMS API через /api/v1/ams/ эндпоинты.
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"
JWT_TOKEN = "YOUR_JWT_TOKEN_HERE"  # Замените на реальный токен

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}"
}

async def test_ams_health():
    """Тест проверки здоровья AMS."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/ams/health")
        print(f"AMS Health: {response.status_code}")
        print(f"Response: {response.json()}")

async def test_get_user_profile():
    """Тест получения профиля пользователя."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/ams/me",
            headers=headers
        )
        print(f"User Profile: {response.status_code}")
        print(f"Response: {response.json()}")

async def test_create_agent():
    """Тест создания агента."""
    payload = {
        "template_id": "test-bot",
        "agent_name": "My Test Agent",
        "use_latest": True,
        "variables": {
            "custom_var": "test_value"
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/ams/agents/create",
            json=payload,
            headers=headers
        )
        print(f"Create Agent: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.json().get('agent_id') if response.status_code == 200 else None

async def test_upgrade_agent(agent_id):
    """Тест обновления агента."""
    if not agent_id:
        print("No agent ID available for upgrade test")
        return
        
    payload = {
        "target_version": "2.0.0",
        "use_latest": False,
        "dry_run": True,
        "use_queue": False
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/ams/agents/{agent_id}/upgrade",
            json=payload,
            headers=headers
        )
        print(f"Upgrade Agent: {response.status_code}")
        print(f"Response: {response.json()}")

async def test_validate_template():
    """Тест валидации шаблона."""
    payload = {
        "template_content": """
af_version: 1
template:
  id: test-bot
  name: Test Bot
  version: 1.0.0
compat:
  letta_min: "1.0.0"
engine:
  model: "gpt-4"
  embedding: "text-embedding-ada-002"
persona:
  system_prompt: "You are a helpful test bot."
""",
        "template_format": "yaml",
        "strict_validation": True
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/ams/templates/validate",
            json=payload,
            headers=headers
        )
        print(f"Validate Template: {response.status_code}")
        print(f"Response: {response.json()}")

async def test_universal_proxy():
    """Тест универсального прокси."""
    # Пример запроса через универсальный прокси
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/ams/agents",
            headers=headers
        )
        print(f"Universal Proxy (list agents): {response.status_code}")
        print(f"Response: {response.json()}")

async def main():
    """Запуск всех тестов."""
    print("🚀 Testing New AMS API")
    print("=" * 50)
    
    print("\n1. Testing AMS Health...")
    await test_ams_health()
    
    print("\n2. Testing User Profile...")
    await test_get_user_profile()
    
    print("\n3. Testing Create Agent...")
    agent_id = await test_create_agent()
    
    print("\n4. Testing Upgrade Agent...")
    await test_upgrade_agent(agent_id)
    
    print("\n5. Testing Validate Template...")
    await test_validate_template()
    
    print("\n6. Testing Universal Proxy...")
    await test_universal_proxy()
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    print("AMS API Examples")
    print("Remember to set JWT_TOKEN variable with your actual token")
    print("=" * 50)
    
    # asyncio.run(main())  # Uncomment to run tests
    print("Uncomment asyncio.run(main()) to run the tests")
