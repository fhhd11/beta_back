# Letta File Upload Support

## Обзор

Прокси для Letta API поддерживает загрузку файлов через `multipart/form-data` запросы. Это позволяет клиентам загружать файлы в папки Letta напрямую через наш шлюз с сохранением JWT-аутентификации и логирования.

## Версия

- **Добавлено в:** dev branch
- **Дата:** 2025-10-10
- **Статус:** В разработке

## Архитектура

### Поддерживаемые типы контента

Прокси теперь поддерживает два типа контента:

1. **`application/json`** - Стандартные JSON запросы (как и раньше)
2. **`multipart/form-data`** - Загрузка файлов с опциональными полями формы

### Обработка запросов

#### JSON запросы
```http
POST /api/v1/letta/agents/{agent_id}/messages
Content-Type: application/json
Authorization: Bearer <JWT_TOKEN>

{
  "message": "Hello",
  "role": "user"
}
```

#### Multipart запросы (загрузка файлов)
```http
POST /api/v1/letta/sources/{source_id}/upload
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary
Authorization: Bearer <JWT_TOKEN>

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

<binary file content>
------WebKitFormBoundary
Content-Disposition: form-data; name="description"

Project documentation
------WebKitFormBoundary--
```

## Технические детали

### Изменения в коде

**Файл:** `src/routers/letta.py`

#### 1. Определение типа запроса
```python
def is_multipart_request(content_type: Optional[str]) -> bool:
    """Check if request is multipart/form-data."""
    if not content_type:
        return False
    return content_type.startswith("multipart/form-data")
```

#### 2. Парсинг multipart данных
```python
if is_multipart:
    form = await request.form()
    files_data = {}
    form_data = {}
    
    for field_name, field_value in form.items():
        if hasattr(field_value, 'file'):
            # Файловое поле
            file_content = await field_value.read()
            files_data[field_name] = (
                field_value.filename,
                file_content,
                field_value.content_type or 'application/octet-stream'
            )
        else:
            # Обычное поле формы
            form_data[field_name] = field_value
```

#### 3. Проксирование файлов в Letta
```python
if is_multipart and files_data:
    request_params["files"] = files_data
    if form_data:
        request_params["data"] = form_data
elif json_data is not None:
    request_params["json"] = json_data
```

### HTTP клиент

HTTP клиент теперь не устанавливает `Content-Type` заголовок глобально, позволяя httpx автоматически устанавливать правильные заголовки для multipart запросов:

```python
_letta_client = httpx.AsyncClient(
    base_url=str(settings.letta_base_url).rstrip('/'),
    timeout=httpx.Timeout(settings.letta_timeout),
    headers={
        "Authorization": f"Bearer {settings.letta_api_key}",
        # Content-Type устанавливается per-request
    },
    follow_redirects=True
)
```

## Логирование

Загрузка файлов подробно логируется:

```python
# При обнаружении multipart запроса
logger.info("Multipart request detected", path=letta_path, user_id=user_id)

# Для каждого файла
logger.debug("File field extracted", 
    field_name=field_name, 
    filename=filename,
    size=len(file_content),
    content_type=content_type
)

# После парсинга
logger.info("Multipart data parsed",
    files_count=len(files_data),
    form_fields_count=len(form_data)
)

# При отправке
logger.info("Sending multipart request",
    files_count=len(files_data),
    form_fields_count=len(form_data)
)
```

## Примеры использования

### Python (requests)

```python
import requests

# Загрузка одного файла
url = "https://your-gateway.com/api/v1/letta/sources/source_123/upload"
headers = {
    "Authorization": f"Bearer {jwt_token}"
}

with open('document.pdf', 'rb') as f:
    files = {'file': ('document.pdf', f, 'application/pdf')}
    data = {'description': 'Important document'}
    
    response = requests.post(url, headers=headers, files=files, data=data)
    print(response.json())
```

### Python (httpx)

```python
import httpx

async with httpx.AsyncClient() as client:
    url = "https://your-gateway.com/api/v1/letta/sources/source_123/upload"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    with open('document.pdf', 'rb') as f:
        files = {'file': ('document.pdf', f, 'application/pdf')}
        data = {'description': 'Important document'}
        
        response = await client.post(url, headers=headers, files=files, data=data)
        print(response.json())
```

### JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('description', 'Important document');

const response = await fetch('https://your-gateway.com/api/v1/letta/sources/source_123/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwtToken}`
    // Content-Type НЕ устанавливается вручную - браузер сделает это автоматически
  },
  body: formData
});

const result = await response.json();
console.log(result);
```

### cURL

```bash
curl -X POST \
  https://your-gateway.com/api/v1/letta/sources/source_123/upload \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "description=Important document"
```

## Безопасность

### Аутентификация
- Все запросы требуют валидный JWT токен
- User ID извлекается из JWT и передается в заголовке `X-User-Id`

### Валидация
- Content-Type проверяется на multipart/form-data
- Ошибки парсинга возвращают HTTP 400
- Применяются те же blacklist правила, что и для JSON запросов

### Ограничения
- Размер файла ограничен настройками FastAPI (по умолчанию нет ограничения)
- Таймаут запроса: `settings.letta_timeout` (по умолчанию 300 секунд)

## Производительность

### Память
- Файлы загружаются в память полностью перед проксированием
- Для больших файлов рекомендуется использовать streaming (future enhancement)

### Таймауты
- Используется тот же таймаут, что и для обычных запросов
- Для больших файлов может потребоваться увеличить `LETTA_TIMEOUT`

## Поддержка стриминга

Текущая реализация поддерживает загрузку файлов в streaming эндпоинтах, если Letta API это позволяет:

```python
if is_streaming:
    request_params = {...}
    if is_multipart and files_data:
        request_params["files"] = files_data
        if form_data:
            request_params["data"] = form_data
    
    async with letta_client.stream(**request_params) as response:
        # Stream response
```

## Известные эндпоинты Letta для файлов

На основе документации Letta API (предположительно):

- `POST /v1/sources/{source_id}/upload` - Загрузка файлов в источник
- `POST /v1/sources/{source_id}/attach` - Прикрепление файлов
- Другие эндпоинты могут быть добавлены по мере необходимости

## Отладка

### Debug эндпоинты

Для проверки конфигурации:

```bash
GET /api/v1/letta/debug/test
GET /api/v1/letta/debug/streaming-patterns
```

### Логи

Уровень логирования можно изменить в `src/config/logging.py`. Для отладки файлов установите:

```python
logger.setLevel("DEBUG")
```

Это покажет детальную информацию о каждом файле и поле формы.

## Troubleshooting

### Проблема: 400 Bad Request при загрузке файла

**Причина:** Неправильный Content-Type или поврежденные multipart данные

**Решение:**
- Убедитесь, что Content-Type установлен как `multipart/form-data`
- Проверьте, что boundary корректный
- Используйте библиотеки, которые автоматически формируют multipart (requests, httpx, FormData)

### Проблема: 413 Request Entity Too Large

**Причина:** Файл слишком большой

**Решение:**
- Увеличьте ограничение в nginx/reverse proxy
- Настройте FastAPI limit:
  ```python
  from fastapi import FastAPI
  app = FastAPI()
  app.add_middleware(RequestSizeLimitMiddleware, max_upload_size=100_000_000)  # 100MB
  ```

### Проблема: 504 Gateway Timeout

**Причина:** Загрузка большого файла занимает слишком много времени

**Решение:**
- Увеличьте `LETTA_TIMEOUT` в переменных окружения
- Проверьте скорость загрузки на Letta API

## Будущие улучшения

### Планируется
- [ ] Streaming upload для больших файлов (chunked upload)
- [ ] Валидация типов файлов на уровне шлюза
- [ ] Ограничение размера файлов в конфигурации
- [ ] Антивирусное сканирование файлов
- [ ] Прогресс загрузки (progress tracking)
- [ ] Поддержка резюмируемых загрузок (resumable uploads)

### В рассмотрении
- Кеширование метаданных файлов
- Сжатие файлов перед отправкой
- Автоматическая конвертация форматов

## Changelog

### [Unreleased] - 2025-10-10
#### Added
- Поддержка multipart/form-data запросов
- Автоматическое определение типа контента
- Парсинг файлов и полей формы
- Проксирование файлов в Letta API
- Детальное логирование загрузки файлов
- Документация по использованию

#### Changed
- HTTP клиент больше не устанавливает Content-Type глобально
- Заголовки Content-Type теперь устанавливаются per-request
- Обновлена документация роутера

## Ссылки

- [Letta API Documentation](https://docs.letta.ai) (если доступно)
- [FastAPI File Upload](https://fastapi.tiangolo.com/tutorial/request-files/)
- [httpx Multipart](https://www.python-httpx.org/advanced/#multipart-file-encoding)

## Контакты

По вопросам и предложениям создавайте issue в репозитории проекта.

