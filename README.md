# AI Agent Gateway - Backend

Backend сервис для AI Agent Gateway, предоставляющий унифицированный API для работы с LLM агентами через Letta и LiteLLM.

## Возможности

- 🔐 **JWT аутентификация** через Supabase
- 🤖 **Управление агентами** через AMS (Agent Management Service)
- 💬 **Прокси для Letta API** с поддержкой стриминга и загрузки файлов
- 🔑 **Управление API ключами** через LiteLLM
- 📊 **Мониторинг и метрики** с детальным логированием
- 🛡️ **Rate limiting** и circuit breaker
- 👨‍💼 **Админ-панель** для управления системой

## Основные компоненты

### Роутеры
- `/api/v1/agents` - Управление AI агентами
- `/api/v1/letta` - Прокси для Letta API (JSON + файлы)
- `/api/v1/llm` - Прокси для LLM запросов
- `/api/v1/templates` - Управление шаблонами агентов
- `/api/v1/me` - Профиль пользователя
- `/api/v1/system` - Системная информация
- `/admin` - Административная панель

### Сервисы
- **AMS Client** - Интеграция с Agent Management Service
- **Letta Client** - HTTP клиент для Letta API
- **LiteLLM Client** - Управление ключами и пользователями
- **Supabase Client** - Аутентификация и хранение данных

## Быстрый старт

### Требования

- Python 3.11+
- Docker и Docker Compose (опционально)
- Доступ к Supabase, LiteLLM и Letta

### Установка

```bash
# Клонирование репозитория
git clone <repository-url>
cd beta_back-master

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения
cp env.example .env
# Отредактируйте .env файл
```

### Конфигурация

Основные переменные окружения (см. `env.example`):

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# LiteLLM
LITELLM_BASE_URL=http://localhost:4000
LITELLM_MASTER_KEY=your-master-key

# Letta
LETTA_BASE_URL=http://localhost:8283
LETTA_API_KEY=your-letta-api-key
LETTA_TIMEOUT=300

# AMS
AMS_BASE_URL=http://localhost:8080
AMS_API_KEY=your-ams-api-key
```

### Запуск

#### Development

```bash
# Локальный запуск
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

#### Docker

```bash
# Development
docker-compose up

# Production
docker-compose -f docker-compose.prod.yml up -d
```

## Документация API

После запуска доступна по адресу:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Дополнительная документация

- [Admin Panel](ADMIN_PANEL.md) - Документация админ-панели
- [Admin Quick Start](ADMIN_QUICK_START.md) - Быстрый старт админки
- [Logging](LOGGING.md) - Конфигурация логирования
- [Logging Optimization](LOGGING_OPTIMIZATION_SUMMARY.md) - Оптимизация логов
- [Letta File Upload](LETTA_FILE_UPLOAD.md) - Загрузка файлов в Letta

## Архитектура

```
src/
├── config/          # Конфигурация (settings, logging)
├── dependencies/    # FastAPI dependencies (auth)
├── middleware/      # Middleware (auth, rate limit, circuit breaker)
├── models/          # Pydantic модели (requests, responses)
├── routers/         # API роутеры
├── services/        # Внешние сервисы (AMS, Letta, LiteLLM, Supabase)
├── templates/       # HTML шаблоны (admin панель)
└── utils/           # Утилиты (cache, context, exceptions, metrics)
```

## Безопасность

- JWT аутентификация для всех эндпоинтов
- Blacklist для опасных операций Letta
- Rate limiting на уровне пользователя
- Circuit breaker для защиты от сбоев upstream сервисов
- Валидация всех входных данных через Pydantic

## Логирование

Используется structured logging через `structlog`:
- JSON формат для production
- Human-readable для development
- Контекстная информация (user_id, request_id, etc.)
- Метрики производительности

Подробнее: [LOGGING.md](LOGGING.md)

## Мониторинг

Доступные метрики:
- Upstream requests (успешные/ошибки)
- Cache hits/misses
- Latency по эндпоинтам
- Rate limiting events

## Development

### Ветки

- `master` - Production-ready код
- `dev` - Development ветка (новые фичи)

### Тестирование

```bash
# Запуск тестов (если настроены)
pytest

# Проверка типов
mypy src/

# Линтер
flake8 src/
```

## Changelog

См. документацию отдельных фич:
- **[2025-10-10]** Добавлена поддержка загрузки файлов в Letta прокси (dev branch) - [LETTA_FILE_UPLOAD.md](LETTA_FILE_UPLOAD.md)

## Лицензия

[Укажите вашу лицензию]

## Поддержка

Для вопросов и предложений создавайте issue в репозитории.

