# AI Agent Platform API Gateway

Production-ready FastAPI gateway for unified access to AI Agent Platform microservices. This gateway replaces the existing Zuplo solution and provides centralized authentication, authorization, and intelligent routing.

## 🚀 Features

### Core Functionality
- **Unified API Gateway**: Single entry point for all AI Agent Platform services
- **JWT Authentication**: Supabase-based authentication with token validation and caching
- **Intelligent Routing**: Path rewriting and security filtering for upstream services
- **Agent Secret Key Auth**: Separate authentication system for internal agent-to-LLM requests

### Performance & Reliability
- **Redis-based Caching**: User profiles, JWT tokens, and agent ownership caching
- **Rate Limiting**: Sliding window rate limiting with different tiers per endpoint category
- **Circuit Breakers**: Automatic failure detection and recovery for upstream services
- **Connection Pooling**: Efficient HTTP client management with connection reuse

### Security
- **Request/Response Filtering**: Hide internal fields and validate operations
- **User Ownership Validation**: Automatic verification of user permissions for resources
- **CORS Support**: Configurable cross-origin resource sharing for frontend integration
- **Idempotency**: Support for safe retries with idempotency keys

### Observability
- **Prometheus Metrics**: Comprehensive metrics for requests, performance, and errors
- **Structured Logging**: JSON-formatted logs with correlation IDs and user context
- **Health Checks**: Detailed health monitoring for all upstream services
- **Request Tracing**: Full request lifecycle tracking with performance metrics

## 🏗️ Architecture

### System Overview
```
Frontend → Python Gateway → [AMS | Letta Server | LiteLLM] → Backend Services
```

### Service Integration
- **AMS (Agent Management Service)**: Supabase Edge Function for agent lifecycle management
- **Letta Server**: Self-hosted agent engine with persistent memory
- **LiteLLM Proxy**: Unified access to various LLM providers
- **Supabase**: PostgreSQL database and authentication service
- **Redis**: Caching and rate limiting backend

## 📋 Prerequisites

- Python 3.11+
- Redis 6.0+
- Docker & Docker Compose (for containerized deployment)
- Access to upstream services (AMS, Letta, LiteLLM, Supabase)

## 🛠️ Installation

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/ai-agent-platform/gateway.git
   cd gateway
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your configuration values
   ```

5. **Start Redis** (if not using Docker)
   ```bash
   redis-server
   ```

6. **Run the application**
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Docker Deployment

1. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your production values
   ```

2. **Start all services**
   ```bash
   docker-compose up -d
   ```

3. **Start with monitoring** (optional)
   ```bash
   docker-compose --profile monitoring up -d
   ```

## ⚙️ Configuration

### Required Environment Variables

```bash
# Service URLs
AMS_BASE_URL=https://your-project.supabase.co/functions/v1/ams
LETTA_BASE_URL=https://your-letta-server.com
LITELLM_BASE_URL=https://your-litellm-proxy.com
SUPABASE_URL=https://your-project.supabase.co

# Authentication
SUPABASE_JWT_SECRET=your-jwt-secret-key
LETTA_API_KEY=your-letta-api-key
AGENT_SECRET_MASTER_KEY=your-agent-secret-key

# Redis
REDIS_URL=redis://localhost:6379
```

See `env.example` for complete configuration options.

### Performance Tuning

```bash
# Adjust based on your load requirements
MAX_CONCURRENT_REQUESTS=1000
REQUEST_TIMEOUT=30.0
LETTA_TIMEOUT=60.0

# Rate limiting (requests per hour per user)
RATE_LIMIT_GENERAL=1000
RATE_LIMIT_LLM=100
RATE_LIMIT_PROXY=500

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
```

## 📚 API Documentation

### Interactive Documentation
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Core Endpoints

#### System Endpoints
- `GET /health` - Comprehensive health check
- `GET /` - API information
- `GET /status` - Detailed system status
- `GET /metrics` - Prometheus metrics

#### User Management
- `GET /api/v1/me` - Get user profile with agents

#### Letta Proxy (Unified)
- `ANY /api/v1/letta/*` - Intelligent proxy with security filtering
- `GET /api/v1/letta/agents` - List user's Letta agents
- `POST /api/v1/letta/agents/{id}/messages` - Send message to agent
- `GET /api/v1/letta/agents/{id}/memory` - Get agent memory
- `PUT /api/v1/letta/agents/{id}/memory` - Update agent memory

#### Agent Management (AMS)
- `POST /api/v1/agents/create` - Create new agent
- `POST /api/v1/agents/{id}/upgrade` - Upgrade agent version
- `GET /api/v1/agents/{id}` - Get agent details
- `GET /api/v1/agents` - List user agents

#### Template Management (AMS)
- `POST /api/v1/templates/validate` - Validate template content
- `POST /api/v1/templates/publish` - Publish template (admin only)

#### LLM Proxy (Internal)
- `POST /api/v1/agents/{user_id}/proxy` - Agent-to-LLM proxy

### Authentication

#### JWT Authentication (Standard)
```bash
curl -H "Authorization: Bearer <jwt_token>" \
     https://api.example.com/api/v1/me
```

#### Agent Secret Key Authentication (Internal)
```bash
curl -H "Authorization: Bearer <agent_secret_key>" \
     https://api.example.com/api/v1/agents/user123/proxy
```

## 🔧 Development

### Project Structure
```
src/
├── main.py                 # FastAPI app entry point
├── config/
│   ├── settings.py         # Environment-based configuration
│   └── logging.py          # Logging configuration
├── middleware/
│   ├── auth.py            # JWT authentication
│   ├── rate_limit.py      # Rate limiting
│   └── circuit_breaker.py # Circuit breaker
├── routers/
│   ├── system.py          # Health, docs endpoints
│   ├── user.py            # User profile management
│   ├── letta.py           # Unified Letta proxy
│   ├── agents.py          # Agent management (AMS proxy)
│   ├── templates.py       # Template management (AMS proxy)
│   └── llm_proxy.py       # Agent-to-LLM proxy
├── services/
│   ├── ams_client.py      # AMS HTTP client
│   └── letta_client.py    # Letta HTTP client
├── models/
│   ├── requests.py        # Request schemas
│   ├── responses.py       # Response schemas
│   └── common.py          # Common models
└── utils/
    ├── cache.py           # Redis caching utilities
    ├── metrics.py         # Prometheus metrics
    └── exceptions.py      # Custom exceptions
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock httpx-mock

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality
```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

## 📊 Monitoring

### Metrics Collection
The gateway exposes Prometheus metrics at `/metrics`:

- **Request Metrics**: Duration, count, status codes
- **Authentication Metrics**: Success/failure rates, JWT validation time
- **Rate Limiting Metrics**: Hits, remaining quotas
- **Circuit Breaker Metrics**: State changes, failure counts
- **Upstream Metrics**: Response times, error rates
- **Cache Metrics**: Hit ratios, operation counts
- **LLM Metrics**: Token usage, model performance

### Health Monitoring
- **Service Health**: Individual upstream service status
- **Circuit Breaker Status**: Current state of all circuit breakers
- **Cache Status**: Redis connectivity and performance
- **System Resources**: Memory usage, active connections

### Logging
Structured JSON logs with:
- Request correlation IDs
- User context information
- Performance metrics
- Error details with stack traces
- Sensitive data filtering

## 🚀 Deployment

### Production Deployment

1. **Build Docker image**
   ```bash
   docker build -t ai-agent-gateway:latest .
   ```

2. **Configure environment**
   ```bash
   # Set production environment variables
   export ENVIRONMENT=production
   export LOG_LEVEL=INFO
   export ENABLE_DOCS=false  # Disable in production
   ```

3. **Deploy with orchestration**
   ```yaml
   # kubernetes/docker-swarm deployment example
   replicas: 3
   resources:
     requests:
       memory: "256Mi"
       cpu: "200m"
     limits:
       memory: "512Mi"
       cpu: "500m"
   ```

### Scaling Considerations

- **Horizontal Scaling**: Stateless design allows multiple replicas
- **Redis Clustering**: Use Redis Cluster for high availability
- **Load Balancing**: Distribute traffic across gateway instances
- **Circuit Breakers**: Prevent cascade failures
- **Rate Limiting**: Distributed rate limiting with Redis

## 🔒 Security

### Authentication Flow
1. Frontend obtains JWT from Supabase Auth
2. Gateway validates JWT signature and expiration
3. User context extracted and cached
4. Requests proxied with user identification

### Security Features
- **JWT Validation**: Cryptographic signature verification
- **Request Filtering**: Whitelist/blacklist for Letta operations
- **Response Filtering**: Remove internal fields from responses
- **User Ownership**: Automatic resource ownership validation
- **Rate Limiting**: Prevent abuse and DoS attacks
- **CORS Policy**: Configurable origin restrictions

### Best Practices
- Use HTTPS in production
- Rotate JWT secrets regularly
- Monitor authentication failures
- Implement proper logging for security events
- Use strong agent secret keys

## 🐛 Troubleshooting

### Common Issues

#### Gateway Won't Start
```bash
# Check environment variables
python -c "from src.config.settings import get_settings; print(get_settings())"

# Verify Redis connectivity
redis-cli ping

# Check logs
docker logs ai-agent-gateway
```

#### Authentication Failures
```bash
# Verify JWT secret
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/me

# Check Supabase configuration
# Ensure JWT_SECRET matches Supabase project settings
```

#### Upstream Service Errors
```bash
# Check service health
curl http://localhost:8000/health

# View circuit breaker status
curl http://localhost:8000/status

# Reset circuit breaker (admin)
curl -X POST http://localhost:8000/admin/circuit-breaker/ams/reset
```

#### Performance Issues
```bash
# Check metrics
curl http://localhost:8000/metrics

# Monitor Redis performance
redis-cli --latency

# Review cache hit ratios in logs
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export DEBUG=true

# Run with verbose output
uvicorn src.main:app --log-level debug
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add tests for new features
- Update documentation
- Ensure all tests pass
- Add type hints

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check `/docs` endpoint for API documentation
- **Issues**: Report bugs on GitHub Issues
- **Monitoring**: Use `/health` and `/status` endpoints for system monitoring
- **Logs**: Check structured logs for detailed error information

## 🔄 Changelog

### v1.0.0 (2025-09-21)
- Initial production release
- Complete FastAPI gateway implementation
- JWT authentication with Supabase integration
- Unified Letta proxy with security filtering
- AMS and template management proxies
- Agent-to-LLM proxy with secret key authentication
- Redis-based caching and rate limiting
- Circuit breaker pattern implementation
- Comprehensive monitoring and metrics
- Docker containerization and orchestration
- Production-ready security and performance optimizations
