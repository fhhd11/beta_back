# Система логирования API Gateway

## Обзор

Проект использует структурированное логирование на основе `structlog` для обеспечения читаемости, производительности и удобства анализа логов в продакшене.

## Конфигурация

### Уровни логирования

- **DEBUG**: Детальная отладочная информация (только для разработки)
- **INFO**: Общая информация о работе приложения
- **WARNING**: Предупреждения о потенциальных проблемах
- **ERROR**: Ошибки, которые не останавливают работу приложения
- **CRITICAL**: Критические ошибки, требующие немедленного внимания

### Форматы логов

- **JSON**: Для продакшена и централизованного сбора логов
- **Console**: Для разработки с цветным выводом

## Структура логов

Каждый лог содержит следующие поля:

```json
{
  "timestamp": "2025-01-06T13:45:10.242Z",
  "level": "info",
  "event": "Request started",
  "service": "api-gateway",
  "environment": "production",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "method": "GET",
  "path": "/api/v1/letta/agents/agent-123/context",
  "client_ip": "192.168.1.1"
}
```

## Оптимизации

### Подавление шумных логгеров

Система автоматически подавляет избыточные логи от сторонних библиотек:

- `httpx`, `httpcore` - HTTP клиенты
- `uvicorn.access`, `uvicorn.error` - Uvicorn сервер
- `asyncio`, `multipart`, `urllib3`, `requests` - Системные библиотеки

### Фильтрация чувствительных данных

Автоматически скрываются следующие поля:
- `password`, `token`, `secret`, `key`
- `authorization`, `jwt`, `api_key`, `bearer`
- `auth`, `credential`

### Фильтрация пустых сообщений

Пустые или содержащие только пробелы сообщения автоматически исключаются из логов.

## Middleware для логирования

### Request Logging Middleware

Единственный middleware для логирования запросов, который:

- Генерирует уникальный `request_id` для каждого запроса
- Логирует только не-OPTIONS запросы для уменьшения шума
- Логирует ошибки (статус >= 400) с деталями
- Пропускает streaming запросы для избежания буферизации
- Добавляет метрики производительности

### Примеры логов

#### Успешный запрос
```json
{
  "timestamp": "2025-01-06T13:45:10.242Z",
  "level": "info",
  "event": "Request started",
  "service": "api-gateway",
  "environment": "production",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "GET",
  "path": "/api/v1/letta/agents/agent-123/context",
  "client_ip": "192.168.1.1"
}
```

#### Ошибка запроса
```json
{
  "timestamp": "2025-01-06T13:45:10.242Z",
  "level": "error",
  "event": "Request failed",
  "service": "api-gateway",
  "environment": "production",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "Connection timeout",
  "duration_ms": 5000.0
}
```

## Использование в коде

### Получение логгера

```python
import structlog

logger = structlog.get_logger(__name__)
```

### Структурированное логирование

```python
# Хорошо - структурированные данные
logger.info(
    "User authenticated",
    user_id=user_id,
    method="jwt",
    duration_ms=150.5
)

# Плохо - неструктурированное сообщение
logger.info(f"User {user_id} authenticated via JWT in 150ms")
```

### Логирование ошибок

```python
try:
    result = await some_operation()
    logger.info("Operation completed", result_size=len(result))
except Exception as e:
    logger.error(
        "Operation failed",
        error=str(e),
        operation="some_operation",
        user_id=user_id
    )
    raise
```

### Логирование производительности

```python
from src.config.logging import log_performance

# Использование как контекстный менеджер
with log_performance("database_query"):
    result = await db.query("SELECT * FROM users")

# Использование как декоратор
@log_performance("user_creation")
async def create_user(user_data):
    return await db.create_user(user_data)
```

## Мониторинг и алерты

### Ключевые метрики

- Время ответа запросов
- Количество ошибок по типам
- Количество запросов по эндпоинтам
- Использование памяти и CPU

### Рекомендуемые алерты

- Ошибки 5xx > 1% от общего количества запросов
- Время ответа > 5 секунд
- Количество критических ошибок > 0

## Переменные окружения

```bash
# Уровень логирования
LOG_LEVEL=INFO

# Формат логов (json/console)
LOG_FORMAT=json

# Включение/выключение документации API
ENABLE_DOCS=false
```

## Лучшие практики

1. **Используйте структурированные данные** вместо форматированных строк
2. **Логируйте контекст** - user_id, request_id, operation
3. **Избегайте логирования чувствительных данных**
4. **Используйте подходящий уровень логирования**
5. **Не логируйте в циклах** без ограничений
6. **Используйте debug уровень** только для отладки
7. **Логируйте ошибки с контекстом** для упрощения диагностики

## Миграция с старой системы

Старые логи с эмодзи и избыточными print() были заменены на структурированные логи:

```python
# Старый способ (удален)
print("🔥🔥🔥 REQUEST RECEIVED 🔥🔥🔥")
logger.critical("🔵🔵🔵 LETTA PROXY CALLED 🔵🔵🔵")

# Новый способ
logger.info(
    "Request received",
    method=request.method,
    path=request.url.path,
    request_id=request_id
)
```

Это обеспечивает:
- Лучшую читаемость
- Упрощенный анализ логов
- Снижение нагрузки на систему
- Соответствие стандартам продакшена
