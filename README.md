# AI Agent Platform API Gateway

🚀 **Production-ready API Gateway** для унифицированного доступа к микросервисам AI Agent Platform.

## 📋 Описание

AI Agent Platform API Gateway - это высокопроизводительный API шлюз, обеспечивающий единую точку входа для всех клиентских приложений к микросервисам платформы. Шлюз предоставляет аутентификацию, авторизацию, мониторинг, кэширование и маршрутизацию запросов.

## ✨ Основные возможности

### 🔐 Безопасность
- **JWT аутентификация** через Supabase
- **Авторизация** на уровне эндпоинтов
- **CORS** поддержка для фронтенд приложений
- **Rate limiting** для защиты от злоупотреблений

### 🚀 Производительность
- **Кэширование** Redis для быстрого доступа
- **Circuit breaker** для отказоустойчивости
- **Асинхронная обработка** запросов
- **Метрики Prometheus** для мониторинга

### 🔌 Интеграции
- **AMS (Agent Management Service)** - управление агентами
- **Letta** - AI агент сервис
- **LiteLLM** - LLM прокси
- **Supabase** - аутентификация и база данных

### 📊 Мониторинг
- **Health checks** для всех сервисов
- **Prometheus метрики** для мониторинга
- **Структурированное логирование** (JSON)
- **Request tracing** с уникальными ID

## 🏗️ Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │───▶│  API Gateway     │───▶│  Microservices  │
│   (React/Vue)   │    │  (FastAPI)       │    │  (AMS/Letta)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Infrastructure  │
                       │  (Redis/Metrics) │
                       └──────────────────┘
```

## 🛠️ Технологический стек

- **FastAPI** - веб-фреймворк
- **Pydantic** - валидация данных
- **Redis** - кэширование
- **Supabase** - аутентификация
- **Prometheus** - метрики
- **Docker** - контейнеризация
- **Railway** - деплой

## 🚀 Быстрый старт

### Локальная разработка

1. **Клонирование репозитория:**
```bash
git clone <repository-url>
cd ai-agent-platform-gateway
```

2. **Установка зависимостей:**
```bash
pip install -r requirements.txt
```

3. **Настройка переменных окружения:**
```bash
cp env.example .env
# Отредактируйте .env файл с вашими настройками
```

4. **Запуск приложения:**
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
# Сборка образа
docker build -t ai-agent-gateway .

# Запуск контейнера
docker run -p 8000:8000 --env-file .env ai-agent-gateway
```

### Railway (Production)

Приложение автоматически деплоится на Railway при push в main ветку.

**Production URL:** https://betaback-production.up.railway.app

## 📚 Документация

- **API документация:** `/docs` (Swagger UI)
- **ReDoc документация:** `/redoc`
- **OpenAPI схема:** `/openapi.json`
- **Клиентская документация:** [API_CLIENT_GUIDE.md](API_CLIENT_GUIDE.md)

## 🔧 Конфигурация

### Обязательные переменные окружения

```env
# Service URLs
AMS_BASE_URL=https://your-ams-service.com
LETTA_BASE_URL=https://your-letta-service.com
LITELLM_BASE_URL=https://your-litellm-service.com
SUPABASE_URL=https://your-project.supabase.co

# Authentication
SUPABASE_JWT_SECRET=your-jwt-secret
SUPABASE_SERVICE_KEY=your-service-key
LETTA_API_KEY=your-letta-key
AGENT_SECRET_MASTER_KEY=your-agent-secret

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://your-frontend.com
```

### Опциональные настройки

```env
# Performance
MAX_CONCURRENT_REQUESTS=1000
REQUEST_TIMEOUT=30.0
RATE_LIMIT_GENERAL=1000

# Redis
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your-redis-password

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## 📊 Мониторинг

### Health Check
```bash
GET /health
```

### Метрики Prometheus
```bash
GET /metrics
```

### Основные эндпоинты
- `GET /ping` - проверка доступности
- `GET /health` - статус всех сервисов
- `GET /docs` - API документация

## 🔒 Безопасность

- Все защищенные эндпоинты требуют JWT токен в заголовке `Authorization: Bearer <token>`
- CORS настроен для безопасной работы с фронтендом
- Rate limiting защищает от злоупотреблений
- Circuit breaker обеспечивает отказоустойчивость

## 🤝 Разработка

### Структура проекта

```
src/
├── config/          # Конфигурация приложения
├── dependencies/    # FastAPI зависимости
├── middleware/      # Middleware компоненты
├── models/          # Pydantic модели
├── routers/         # API роутеры
├── services/        # Внешние сервисы
└── utils/           # Утилиты
```

### Запуск тестов

```bash
pytest tests/
```

### Линтинг

```bash
black src/
isort src/
flake8 src/
mypy src/
```

## 📄 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для деталей.

## 🆘 Поддержка

Для вопросов и поддержки:
- Создайте issue в репозитории
- Обратитесь к [API_CLIENT_GUIDE.md](API_CLIENT_GUIDE.md) для работы с API
- Проверьте `/docs` для интерактивной документации

---

**Версия:** 1.0.0  
**Статус:** Production Ready ✅