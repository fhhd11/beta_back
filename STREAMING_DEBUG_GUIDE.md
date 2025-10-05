# Руководство по отладке стриминга LLM прокси

## 🔍 Диагностика проблем со стримингом

### Симптомы проблем

1. **Прокси закрывает апстрим быстро:**
   ```
   receive_response_body.started
   receive_response_body.complete  ← Происходит мгновенно
   response_closed.complete
   ```

2. **Фронт видит только часть данных:**
   - ✅ `reasoning_message` - отображается
   - ✅ `stop_reason` - отображается  
   - ✅ `usage_statistics` - отображается
   - ❌ `assistant_message` - НЕ отображается
   - ❌ `tool_result` с `send_message` - НЕ отображается

### 🔧 Исправления на бэкенде

#### 1. Отключена буферизация middleware
```python
# В src/main.py - middleware пропускает стриминговые запросы
if (request.url.path.endswith("/proxy") or 
    request.url.path.endswith("/chat/completions") or
    "stream" in request.url.path or
    request.headers.get("accept") == "text/event-stream"):
    return await call_next(request)  # Пропускаем middleware
```

#### 2. Исправлены CORS заголовки для стриминга
```python
# В src/routers/letta.py - убраны конфликтующие CORS заголовки
response_headers = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # Disable nginx buffering
    "X-Content-Type-Options": "nosniff",
    "Transfer-Encoding": "chunked",
}
```

#### 3. Оптимизирован размер чанков
```python
# Используем chunk_size=512 для лучшей отзывчивости
async for chunk in response.aiter_bytes(chunk_size=512):
    if chunk:
        yield chunk  # Немедленная передача
```

#### 4. Добавлено детальное логирование
```python
logger.info("Starting stream forwarding", 
           path=letta_path,
           content_type=response.headers.get("content-type"),
           response_headers=dict(response.headers))

logger.info("First streaming chunk",
           chunk_preview=chunk[:100].decode('utf-8', errors='ignore'))
```

#### 5. Пропуск CORS middleware для стриминга
```python
# В src/main.py - CORS middleware пропускает стриминговые запросы
if (request.url.path.endswith("/stream") or 
    "stream" in request.url.path or
    request.headers.get("accept") == "text/event-stream"):
    return await call_next(request)
```

### 📱 Обработка на фронтенде

#### Проблема: Основной текст не отображается

Текст может находиться в разных местах ответа:

1. **В `assistant_message.content`** (стандартное место)
2. **В `tool_result.content`** (если используется инструмент)
3. **В `usage_statistics.steps_messages[*]`** (Letta специфично)

#### Решение: Проверяйте все возможные места

```javascript
function extractMessageContent(streamData) {
  // 1. Проверяем assistant_message
  if (streamData.assistant_message?.content) {
    return streamData.assistant_message.content;
  }
  
  // 2. Проверяем tool_result (для send_message)
  if (streamData.tool_result) {
    const sendMessageTool = streamData.tool_result.find(
      tool => tool.function_name === 'send_message'
    );
    if (sendMessageTool?.content) {
      return sendMessageTool.content;
    }
  }
  
  // 3. Проверяем steps_messages (Letta специфично)
  if (streamData.usage_statistics?.steps_messages) {
    const lastStep = streamData.usage_statistics.steps_messages[
      streamData.usage_statistics.steps_messages.length - 1
    ];
    if (lastStep?.content) {
      return lastStep.content;
    }
  }
  
  return null;
}
```

#### Полный пример обработки SSE

```javascript
const eventSource = new EventSource('/api/v1/agents/{user_id}/proxy/chat/completions');

eventSource.onmessage = function(event) {
  try {
    const data = JSON.parse(event.data);
    
    // Извлекаем контент из всех возможных мест
    const messageContent = extractMessageContent(data);
    
    if (messageContent) {
      // Отображаем основной текст
      displayMessage(messageContent);
    }
    
    // Обрабатываем reasoning
    if (data.reasoning_message) {
      displayReasoning(data.reasoning_message);
    }
    
    // Обрабатываем статистику
    if (data.usage_statistics) {
      updateUsageStats(data.usage_statistics);
    }
    
  } catch (error) {
    console.error('Error parsing SSE data:', error);
  }
};
```

### 🐛 Отладка

#### 1. Проверьте логи бэкенда
Ищите сообщения:
- `=== STREAMING REQUEST STARTED ===`
- `=== UPSTREAM CONNECTION ESTABLISHED ===`
- `=== STREAMING PROGRESS ===`
- `=== STREAMING COMPLETED ===`

#### 2. Проверьте заголовки ответа
```bash
curl -H "Accept: text/event-stream" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -N \
     http://your-backend/api/v1/agents/{user_id}/proxy/chat/completions
```

Должны быть заголовки:
```
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
Transfer-Encoding: chunked
```

#### 3. Проверьте структуру данных
Логируйте полную структуру каждого SSE события:
```javascript
eventSource.onmessage = function(event) {
  console.log('Full SSE data:', JSON.parse(event.data));
};
```

### ✅ Ожидаемое поведение после исправлений

1. **В логах должно быть:**
   ```
   === STREAMING REQUEST STARTED ===
   === UPSTREAM CONNECTION ESTABLISHED ===
   === STREAMING PROGRESS === (каждые 5 сек или 100 чанков)
   === STREAMING COMPLETED ===
   ```

2. **Запрос должен "висеть" до конца стрима:**
   - `receive_response_body.complete` происходит в конце
   - Не мгновенно после `receive_response_body.started`

3. **Фронт должен получать:**
   - ✅ Все токены в реальном времени
   - ✅ Основной текст (из любого места в структуре)
   - ✅ Reasoning сообщения
   - ✅ Статистику использования

### 🚨 Если проблема остается

1. **Проверьте nginx конфигурацию:**
   ```nginx
   proxy_buffering off;
   proxy_cache off;
   ```

2. **Проверьте CDN/Edge настройки:**
   - Должен быть заголовок `Cache-Control: no-transform`
   - Отключите компрессию для `text/event-stream`

3. **Проверьте браузерные DevTools:**
   - Network tab → Response должен показывать поток
   - Не должен быть один большой блок в конце

---

**Последнее обновление:** 2025-01-27  
**Версия исправлений:** b452e28
