# Quick Start Guide

## 🚀 Quick Start (5 minutes)

### 1. Prerequisites
- Python 3.11+
- Redis (or use Docker)
- Git

### 2. Setup
```bash
# Clone and setup
git clone https://github.com/ai-agent-platform/gateway.git
cd gateway
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp env.example .env
# Edit .env with your values (see Required Configuration below)
```

### 3. Start Services
```bash
# Option A: Use Docker for Redis + Gateway
docker-compose up -d

# Option B: Local development
redis-server &  # Start Redis
python run.py   # Start gateway
```

### 4. Test
```bash
# Health check
curl http://localhost:8000/health

# API documentation
open http://localhost:8000/docs
```

## 📋 Required Configuration

Edit `.env` with these **required** values:

```bash
# Service URLs
AMS_BASE_URL=https://your-project.supabase.co/functions/v1/ams
LETTA_BASE_URL=https://your-letta-server.com  
LITELLM_BASE_URL=https://your-litellm-proxy.com
SUPABASE_URL=https://your-project.supabase.co

# Authentication  
SUPABASE_JWT_SECRET=your-jwt-secret-from-supabase
LETTA_API_KEY=your-letta-api-key
AGENT_SECRET_MASTER_KEY=your-generated-secret-key

# CORS (for frontend)
ALLOWED_ORIGINS=http://localhost:3000,https://your-frontend.com
```

## 🔧 Common Commands

```bash
# Development
python run.py                    # Start dev server
python -m pytest tests/         # Run tests
docker-compose up -d            # Start with Docker

# Production
docker-compose -f docker-compose.prod.yml up -d

# Monitoring
docker-compose --profile monitoring up -d  # Include Grafana/Prometheus
open http://localhost:3000                  # Grafana (admin/admin)
open http://localhost:9090                  # Prometheus
```

## 🧪 Testing the API

### Authentication
```bash
# Get JWT from your Supabase Auth
TOKEN="your-jwt-token"

# Test authenticated endpoints
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/me
```

### Agent Operations  
```bash
# Create agent
curl -X POST http://localhost:8000/api/v1/agents/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Agent", "description": "My test agent"}'

# List agents
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/agents
```

### Letta Proxy
```bash
# Send message to Letta agent
curl -X POST http://localhost:8000/api/v1/letta/agents/AGENT_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "role": "user"}'
```

## 🔍 Troubleshooting

### Gateway won't start
```bash
# Check environment
python -c "from src.config.settings import get_settings; print(get_settings())"

# Check Redis
redis-cli ping  # Should return PONG

# Check logs
docker logs ai-agent-gateway
```

### Authentication issues
- Verify `SUPABASE_JWT_SECRET` matches your Supabase project
- Check JWT token is valid and not expired
- Ensure `SUPABASE_URL` is correct

### Upstream service errors
```bash
# Check service health
curl http://localhost:8000/health

# View detailed status  
curl http://localhost:8000/status
```

## 📚 Next Steps

1. **Read the full [README.md](README.md)** for complete documentation
2. **Configure production settings** in `.env`
3. **Set up monitoring** with Grafana dashboards
4. **Implement proper secrets management** for production
5. **Configure load balancing** for high availability

## 🆘 Need Help?

- **API Docs**: http://localhost:8000/docs
- **Health Status**: http://localhost:8000/health  
- **System Status**: http://localhost:8000/status
- **Metrics**: http://localhost:8000/metrics
- **Full Documentation**: [README.md](README.md)
