# Руководство по работе с AI Agent Platform API Gateway

## 📖 Введение

Данное руководство описывает полный процесс работы с AI Agent Platform API Gateway. API Gateway служит единой точкой входа для всех клиентских приложений, обеспечивая аутентификацию, авторизацию и маршрутизацию запросов к микросервисам платформы.

**Base URL:** `https://betaback-production.up.railway.app`

## 🔐 Аутентификация

### Обзор системы аутентификации

API Gateway использует JWT (JSON Web Token) аутентификацию через Supabase. Все защищенные эндпоинты требуют валидный JWT токен в заголовке запроса.

### Получение JWT токена

JWT токен получается через Supabase Auth на фронтенде:

1. **Регистрация/Вход пользователя** через Supabase Auth
2. **Получение токена** из Supabase Auth session
3. **Передача токена** в заголовке `Authorization: Bearer <token>`

### Формат токена

JWT токен содержит следующую информацию:
- `sub` - уникальный ID пользователя
- `email` - email пользователя
- `role` - роль пользователя (обычно "authenticated")
- `aud` - аудитория токена ("authenticated")
- `iss` - издатель токена (Supabase URL)
- `exp` - время истечения токена
- `iat` - время создания токена

### Использование токена

Все защищенные запросы должны содержать заголовок:
```
Authorization: Bearer <your-jwt-token>
```

### Обработка ошибок аутентификации

- **401 Unauthorized** - токен отсутствует или недействителен
- **403 Forbidden** - токен валиден, но недостаточно прав
- **422 Unprocessable Entity** - токен имеет неправильный формат

## 🌐 CORS (Cross-Origin Resource Sharing)

### Настройка CORS

API Gateway настроен для работы с фронтенд приложениями. Поддерживаются следующие настройки:

- **Разрешенные домены:** Настраиваются через переменную `ALLOWED_ORIGINS`
- **Разрешенные методы:** GET, POST, PUT, DELETE, OPTIONS, PATCH
- **Разрешенные заголовки:** Authorization, Content-Type, Origin, и другие
- **Credentials:** Поддерживаются (cookies, authorization headers)

### Preflight запросы

Браузер автоматически отправляет OPTIONS запросы для проверки CORS. API Gateway корректно обрабатывает эти запросы и возвращает необходимые заголовки.

#### Диагностика проблем с CORS

Если возникают проблемы с CORS, используйте следующие методы диагностики:

1. **Проверка конфигурации CORS:**
   ```bash
   GET /cors-debug
   ```
   Этот эндпоинт показывает текущую конфигурацию CORS.

2. **Проверка preflight запросов:**
   ```bash
   OPTIONS /api/v1/me
   ```
   Проверьте заголовки ответа на наличие `Access-Control-Allow-Origin`.

3. **Проверка логов приложения:**
   - Логи содержат детальную информацию о парсинге CORS конфигурации
   - Ищите сообщения с "CORS parsing" и "CORS request"

#### Устранение неполадок

- **Ошибка "No 'Access-Control-Allow-Origin' header":**
  - Проверьте переменную окружения `ALLOWED_ORIGINS`
  - Убедитесь, что домен фронтенда включен в список разрешенных
  - Проверьте логи приложения на предмет ошибок парсинга

- **CORS работает в development, но не в production:**
  - Проверьте переменные окружения в Railway
  - Убедитесь, что используется HTTPS для production доменов

## 📡 Основные эндпоинты

### Системные эндпоинты

#### Health Check
**GET** `/health`

Проверяет статус всех подключенных сервисов и возвращает общее состояние системы.

**Ответ:**
- `status` - общий статус системы (success/degraded/error)
- `message` - описание состояния
- `services` - массив статусов всех сервисов
- `overall_status` - общий статус (healthy/degraded/unhealthy)
- `version` - версия API Gateway
- `timestamp` - время проверки

#### Ping
**GET** `/ping`

Простая проверка доступности API Gateway.

**Ответ:**
- `status` - "ok"
- `timestamp` - текущее время в ISO формате

### Пользовательские эндпоинты

#### Получение информации о пользователе
**GET** `/api/v1/me`

Возвращает информацию о текущем аутентифицированном пользователе.

**Требования:**
- JWT токен в заголовке Authorization

**Ответ:**
- Информация о пользователе из AMS сервиса
- Список агентов пользователя
- Метаданные профиля

### AMS (Agent Management Service) - Унифицированный интерфейс

Все операции с агентами и шаблонами теперь доступны через единый эндпоинт `/api/v1/ams/`.

#### Проверка здоровья AMS
**GET** `/api/v1/ams/health`

Проверяет доступность AMS сервиса.

#### Получение профиля пользователя
**GET** `/api/v1/ams/me`

Возвращает информацию о текущем пользователе и его агентах.

**Требования:**
- JWT токен в заголовке Authorization

**Ответ:**
- Информация о пользователе
- Список агентов пользователя
- Метаданные профиля

#### Создание агента
**POST** `/api/v1/ams/agents/create`

Создает нового агента для пользователя.

**Требования:**
- JWT токен в заголовке Authorization
- Данные агента в теле запроса

**Тело запроса:**
```json
{
  "template_id": "test-bot",
  "agent_name": "My Test Agent",
  "use_latest": true,
  "variables": {
    "custom_var": "value"
  }
}
```

#### Обновление агента
**POST** `/api/v1/ams/agents/{agent_id}/upgrade`

Обновляет агента до новой версии.

**Требования:**
- JWT токен в заголовке Authorization
- ID агента в URL

**Тело запроса:**
```json
{
  "target_version": "2.0.0",
  "use_latest": false,
  "dry_run": true,
  "use_queue": false
}
```

### Управление шаблонами

#### Валидация шаблона
**POST** `/api/v1/ams/templates/validate`

Валидирует содержимое шаблона.

**Требования:**
- JWT токен в заголовке Authorization
- Содержимое шаблона в теле запроса

**Тело запроса:**
```json
{
  "template_content": "af_version: 1\ntemplate:\n  id: test-bot\n  name: Test Bot\n  version: 1.0.0\n...",
  "template_format": "yaml",
  "strict_validation": true
}
```

#### Публикация шаблона
**POST** `/api/v1/ams/templates/publish`

Публикует новый шаблон или версию шаблона.

**Требования:**
- JWT токен в заголовке Authorization
- Содержимое шаблона в теле запроса

**Тело запроса:**
```json
{
  "template_id": "test-bot",
  "version": "1.0.0",
  "is_public": true,
  "changelog": "Initial release",
  "tags": ["support", "customer-service"]
}
```

### Универсальный прокси

Для любых других операций с AMS можно использовать универсальный эндпоинт:

**ANY** `/api/v1/ams/{path}`

Где `{path}` - любой путь к AMS эндпоинту. Например:
- `/api/v1/ams/agents/list` - список агентов
- `/api/v1/ams/templates/list` - список шаблонов
- `/api/v1/ams/agents/{agent_id}` - информация об агенте

#### Удаление агента
**DELETE** `/api/v1/agents/{agent_id}`

Удаляет агента пользователя.

**Требования:**
- JWT токен в заголовке Authorization
- ID агента в URL

### Шаблоны агентов

#### Валидация шаблона
**POST** `/api/v1/templates/validate`

Валидирует содержимое шаблона агента.

**Требования:**
- JWT токен в заголовке Authorization
- Данные шаблона в теле запроса

**Тело запроса:**
- `content` - содержимое шаблона (YAML или JSON)
- `format` - формат шаблона ("yaml" или "json")

**Ответ:**
- `valid` - булево значение валидности
- `errors` - массив ошибок валидации (если есть)
- `warnings` - массив предупреждений (если есть)

#### Публикация шаблона
**POST** `/api/v1/templates/publish`

Публикует шаблон агента.

**Требования:**
- JWT токен в заголовке Authorization
- Административные права
- Данные шаблона в теле запроса

### Letta интеграция

#### Прокси к Letta API
**POST** `/api/v1/letta/{path:path}`

Проксирует запросы к Letta сервису.

**Требования:**
- JWT токен в заголовке Authorization
- Путь к Letta эндпоинту в URL

**Особенности:**
- Автоматическое добавление заголовков авторизации
- Проксирование тела запроса
- Возврат ответа от Letta сервиса

### LLM Proxy

#### Прокси к LiteLLM
**POST** `/api/v1/agents/{agent_id}/proxy`

Проксирует запросы к LLM через LiteLLM сервис.

**Требования:**
- JWT токен в заголовке Authorization
- ID агента в URL
- Данные запроса в теле

**Особенности:**
- Автоматическая авторизация через Agent Secret Key
- Маршрутизация к соответствующему LLM
- Обработка ошибок и таймаутов

## 📊 Мониторинг и метрики

### Prometheus метрики
**GET** `/metrics`

Возвращает метрики в формате Prometheus для мониторинга.

**Доступные метрики:**
- `http_requests_total` - общее количество запросов
- `http_request_duration_seconds` - время выполнения запросов
- `auth_attempts_total` - попытки аутентификации
- `circuit_breaker_state` - состояние circuit breaker

### Логирование

API Gateway использует структурированное логирование в JSON формате. Каждый запрос логируется с:
- Уникальным request_id
- Временем выполнения
- Статус кодом ответа
- Информацией о пользователе (если аутентифицирован)

## ⚡ Rate Limiting

### Ограничения скорости

API Gateway применяет ограничения скорости для защиты от злоупотреблений:

- **Общие запросы:** 1000 запросов в час на пользователя
- **LLM запросы:** 100 запросов в час на пользователя
- **Proxy запросы:** 500 запросов в час на пользователя

### Заголовки Rate Limiting

Ответы содержат заголовки с информацией об ограничениях:
- `X-RateLimit-Limit` - лимит запросов
- `X-RateLimit-Remaining` - оставшиеся запросы
- `X-RateLimit-Reset` - время сброса лимита

### Обработка превышения лимита

При превышении лимита возвращается:
- **429 Too Many Requests**
- Информация о времени сброса лимита
- Рекомендации по оптимизации запросов

## 🔄 Circuit Breaker

### Отказоустойчивость

API Gateway использует Circuit Breaker паттерн для обеспечения отказоустойчивости при работе с внешними сервисами.

### Состояния Circuit Breaker

- **CLOSED** - нормальная работа, запросы проходят
- **OPEN** - сервис недоступен, запросы блокируются
- **HALF_OPEN** - тестирование восстановления сервиса

### Настройки

- **Failure Threshold:** 5 неудачных запросов подряд
- **Recovery Timeout:** 60 секунд
- **Expected Exceptions:** все исключения считаются неудачными

## 🗄️ Кэширование

### Redis кэширование

API Gateway использует Redis для кэширования часто запрашиваемых данных:

- **JWT валидация:** 5 минут
- **Пользовательские профили:** 5 минут
- **Права доступа:** 10 минут
- **Health checks:** 1 минута

### Стратегии кэширования

- **Write-through** - данные записываются в кэш при обновлении
- **TTL-based** - автоматическое истечение кэша
- **Invalidation** - принудительная очистка кэша

## 🚨 Обработка ошибок

### Стандартный формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "status": "error",
  "message": "Описание ошибки",
  "timestamp": "2025-09-21T14:00:00Z",
  "request_id": "unique-request-id",
  "error": {
    "code": "ERROR_CODE",
    "message": "Детальное описание",
    "context": {
      "additional_info": "value"
    }
  }
}
```

### Коды ошибок

- **AUTHENTICATION_ERROR** - проблемы с аутентификацией
- **AUTHORIZATION_ERROR** - недостаточно прав
- **VALIDATION_ERROR** - ошибки валидации данных
- **NOT_FOUND** - ресурс не найден
- **RATE_LIMIT_EXCEEDED** - превышен лимит запросов
- **SERVICE_UNAVAILABLE** - внешний сервис недоступен
- **INTERNAL_ERROR** - внутренняя ошибка сервера

### HTTP статус коды

- **200 OK** - успешный запрос
- **201 Created** - ресурс создан
- **400 Bad Request** - неверный запрос
- **401 Unauthorized** - не аутентифицирован
- **403 Forbidden** - недостаточно прав
- **404 Not Found** - ресурс не найден
- **422 Unprocessable Entity** - ошибка валидации
- **429 Too Many Requests** - превышен лимит
- **500 Internal Server Error** - внутренняя ошибка
- **503 Service Unavailable** - сервис недоступен

## 🔧 Конфигурация клиента

### Базовые настройки

```javascript
const API_BASE_URL = 'https://betaback-production.up.railway.app';
const API_TIMEOUT = 30000; // 30 секунд
```

### Заголовки по умолчанию

```javascript
const defaultHeaders = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'User-Agent': 'YourApp/1.0.0'
};
```

### Обработка аутентификации

```javascript
// Получение токена из Supabase
const { data: { session } } = await supabase.auth.getSession();
const token = session?.access_token;

// Добавление токена к запросам
const authHeaders = {
  ...defaultHeaders,
  'Authorization': `Bearer ${token}`
};
```

### Обработка ошибок

```javascript
try {
  const response = await fetch(`${API_BASE_URL}/api/v1/me`, {
    headers: authHeaders
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message);
  }
  
  const data = await response.json();
  return data;
} catch (error) {
  console.error('API Error:', error);
  throw error;
}
```

## 📱 Рекомендации по использованию

### Оптимизация запросов

1. **Используйте кэширование** - API Gateway кэширует часто запрашиваемые данные
2. **Группируйте запросы** - избегайте множественных последовательных запросов
3. **Обрабатывайте ошибки** - всегда проверяйте статус ответа
4. **Используйте retry логику** - для временных ошибок сети

### Безопасность

1. **Никогда не храните JWT токены** в localStorage без шифрования
2. **Обновляйте токены** перед истечением срока действия
3. **Используйте HTTPS** для всех запросов
4. **Валидируйте данные** на клиенте перед отправкой

### Производительность

1. **Используйте pagination** для больших списков
2. **Реализуйте debouncing** для поисковых запросов
3. **Кэшируйте данные** на клиенте
4. **Используйте WebSocket** для real-time обновлений (если поддерживается)

## 🔍 Отладка

### Логирование запросов

Включите детальное логирование для отладки:

```javascript
const debugRequest = async (url, options) => {
  console.log('Request:', { url, options });
  const response = await fetch(url, options);
  console.log('Response:', {
    status: response.status,
    headers: Object.fromEntries(response.headers.entries())
  });
  return response;
};
```

### Проверка CORS

Убедитесь, что ваш домен добавлен в `ALLOWED_ORIGINS`:

```bash
curl -H "Origin: https://your-domain.com" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     https://betaback-production.up.railway.app/health
```

### Проверка аутентификации

Проверьте валидность JWT токена:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://betaback-production.up.railway.app/api/v1/me
```

## 📞 Поддержка

### Получение помощи

1. **Проверьте документацию** - `/docs` для интерактивной документации
2. **Проверьте статус** - `/health` для состояния сервисов
3. **Проверьте логи** - используйте request_id для отслеживания запросов
4. **Создайте issue** - в репозитории проекта

### Полезные ссылки

- **API документация:** https://betaback-production.up.railway.app/docs
- **Health check:** https://betaback-production.up.railway.app/health
- **OpenAPI схема:** https://betaback-production.up.railway.app/openapi.json

---

**Версия API:** 1.0.0  
**Последнее обновление:** 21 сентября 2025
