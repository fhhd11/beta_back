# Руководство по разработке фронтенда для AI Agent Platform

## 📖 Введение

Данное руководство описывает полный процесс разработки фронтенд приложений для AI Agent Platform. Вы узнаете, как интегрироваться с API Gateway, работать с агентами через Letta API, и использовать все возможности платформы.

**Base URL:** `https://betaback-production.up.railway.app`

## 🏗️ Архитектура системы

### Общая схема

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

### Микросервисы

1. **API Gateway** - единая точка входа для всех запросов
2. **AMS (Agent Management Service)** - управление агентами и шаблонами
3. **Letta** - AI агент движок для выполнения задач
4. **LiteLLM** - прокси для доступа к языковым моделям
5. **Supabase** - аутентификация и база данных

## 🔐 Аутентификация

### JWT Аутентификация через Supabase

Все защищенные эндпоинты требуют JWT токен в заголовке `Authorization: Bearer <token>`.

#### Получение токена

```javascript
// Используя Supabase клиент
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://your-project.supabase.co',
  'your-anon-key'
)

// Регистрация/Вход
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password'
})

// Получение токена
const { data: { session } } = await supabase.auth.getSession()
const token = session?.access_token
```

#### Использование токена в запросах

```javascript
const API_BASE_URL = 'https://betaback-production.up.railway.app'

const apiClient = {
  async request(endpoint, options = {}) {
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
      }
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.message || 'Request failed')
    }

    return response.json()
  }
}
```

### Agent Secret Key (для внутренних запросов)

Для запросов от агентов к LLM используется специальный Agent Secret Key:

```javascript
// Для LLM proxy запросов
const agentSecretKey = 'your-agent-secret-key'

const llmResponse = await fetch(`${API_BASE_URL}/api/v1/agents/${userId}/proxy`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${agentSecretKey}`
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [{ role: 'user', content: 'Hello!' }]
  })
})
```

## 🚀 Основные API эндпоинты

### Системные эндпоинты

#### Health Check
```javascript
// Проверка состояния всех сервисов
const health = await apiClient.request('/health')
console.log(health)
// {
//   "status": "success",
//   "message": "All services are healthy",
//   "services": {
//     "ams": "healthy",
//     "letta": "healthy",
//     "litellm": "healthy"
//   },
//   "overall_status": "healthy",
//   "version": "1.0.0",
//   "timestamp": "2025-01-21T10:00:00Z"
// }
```

#### Ping
```javascript
// Простая проверка доступности
const ping = await apiClient.request('/ping')
// { "status": "ok", "timestamp": "2025-01-21T10:00:00Z" }
```

### Пользовательские эндпоинты

#### Получение профиля пользователя
```javascript
const profile = await apiClient.request('/api/v1/me')
console.log(profile)
// {
//   "user_id": "uuid",
//   "email": "user@example.com",
//   "display_name": "John Doe",
//   "role": "authenticated",
//   "agents": [
//     {
//       "agent_id": "agent-123",
//       "name": "My Assistant",
//       "status": "active",
//       "created_at": "2025-01-21T10:00:00Z"
//     }
//   ]
// }
```

## 🤖 Работа с агентами через AMS

### Создание агента

```javascript
const createAgent = async (templateId, agentName, variables = {}) => {
  return await apiClient.request('/api/v1/ams/agents/create', {
    method: 'POST',
    body: JSON.stringify({
      template_id: templateId,
      agent_name: agentName,
      use_latest: true,
      variables: variables
    })
  })
}

// Пример использования
const newAgent = await createAgent('customer-support-bot', 'My Support Bot', {
  company_name: 'My Company',
  support_email: 'support@mycompany.com'
})
```

### Обновление агента

```javascript
const upgradeAgent = async (agentId, targetVersion) => {
  return await apiClient.request(`/api/v1/ams/agents/${agentId}/upgrade`, {
    method: 'POST',
    body: JSON.stringify({
      target_version: targetVersion,
      use_latest: false,
      dry_run: false,
      use_queue: false
    })
  })
}
```

### Получение списка агентов

```javascript
const getAgents = async () => {
  return await apiClient.request('/api/v1/ams/agents/list')
}
```

## 🧠 Работа с Letta API

### Обзор Letta API

Letta предоставляет мощный API для работы с AI агентами. Согласно [официальной документации](https://docs.letta.com/api-reference/overview), Letta поддерживает:

- **Agents** - создание и управление агентами
- **Messages** - отправка сообщений и получение ответов
- **Memory** - управление памятью агентов
- **Tools** - интеграция с внешними инструментами
- **Sources** - работа с документами и файлами

### Подключение к Letta через API Gateway

Наш API Gateway предоставляет прокси к Letta API с автоматической аутентификацией:

```javascript
// Базовый URL для Letta запросов
const LETTA_BASE_URL = '/api/v1/letta'
```

### Работа с агентами Letta

#### Получение списка агентов

```javascript
const getLettaAgents = async () => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents`)
}

// Пример ответа
const agents = await getLettaAgents()
console.log(agents)
// [
//   {
//     "id": "agent-123",
//     "name": "Customer Support Agent",
//     "description": "AI assistant for customer support",
//     "status": "active",
//     "created_at": "2025-01-21T10:00:00Z"
//   }
// ]
```

#### Получение информации об агенте

```javascript
const getLettaAgent = async (agentId) => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents/${agentId}`)
}
```

#### Отправка сообщения агенту

```javascript
const sendMessageToAgent = async (agentId, message, options = {}) => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents/${agentId}/messages`, {
    method: 'POST',
    body: JSON.stringify({
      message: message,
      stream: options.stream || false,
      ...options
    })
  })
}

// Пример использования
const response = await sendMessageToAgent('agent-123', 'Hello, how can you help me?')
console.log(response)
// {
//   "id": "msg-456",
//   "content": "Hello! I'm here to help you with any questions...",
//   "role": "assistant",
//   "created_at": "2025-01-21T10:00:00Z"
// }
```

#### Получение истории сообщений

```javascript
const getAgentMessages = async (agentId, limit = 50, offset = 0) => {
  return await apiClient.request(
    `${LETTA_BASE_URL}/agents/${agentId}/messages?limit=${limit}&offset=${offset}`
  )
}
```

### Управление памятью агентов

#### Получение памяти агента

```javascript
const getAgentMemory = async (agentId) => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents/${agentId}/memory`)
}
```

#### Обновление памяти агента

```javascript
const updateAgentMemory = async (agentId, memoryData) => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents/${agentId}/memory`, {
    method: 'PUT',
    body: JSON.stringify(memoryData)
  })
}
```

#### Работа с архивной памятью

```javascript
// Получение архивной памяти
const getArchivalMemory = async (agentId, query = null, limit = 10) => {
  const params = new URLSearchParams()
  if (query) params.append('query', query)
  if (limit) params.append('limit', limit)
  
  return await apiClient.request(
    `${LETTA_BASE_URL}/agents/${agentId}/archival?${params}`
  )
}

// Добавление в архивную память
const addToArchivalMemory = async (agentId, content) => {
  return await apiClient.request(`${LETTA_BASE_URL}/agents/${agentId}/archival`, {
    method: 'POST',
    body: JSON.stringify({
      content: content
    })
  })
}
```

### Работа с инструментами (Tools)

Согласно документации Letta, агенты могут использовать различные инструменты:

```javascript
// Получение списка доступных инструментов
const getTools = async () => {
  return await apiClient.request(`${LETTA_BASE_URL}/tools`)
}

// Получение информации об инструменте
const getTool = async (toolId) => {
  return await apiClient.request(`${LETTA_BASE_URL}/tools/${toolId}`)
}
```

### Работа с источниками данных (Sources)

```javascript
// Получение списка источников
const getSources = async () => {
  return await apiClient.request(`${LETTA_BASE_URL}/sources`)
}

// Загрузка файла в источник
const uploadFileToSource = async (sourceId, file) => {
  const formData = new FormData()
  formData.append('file', file)
  
  return await fetch(`${API_BASE_URL}${LETTA_BASE_URL}/sources/${sourceId}/files`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  })
}
```

## 🔄 LLM Proxy для прямого доступа к языковым моделям

### Отправка запросов к LLM

```javascript
const sendLLMRequest = async (userId, requestData) => {
  return await apiClient.request(`/api/v1/agents/${userId}/proxy`, {
    method: 'POST',
    body: JSON.stringify(requestData)
  })
}

// Пример использования
const llmResponse = await sendLLMRequest('user-123', {
  model: 'gpt-4',
  messages: [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'user', content: 'Explain quantum computing in simple terms.' }
  ],
  temperature: 0.7,
  max_tokens: 1000
})
```

### Streaming запросы

```javascript
const sendStreamingLLMRequest = async (userId, requestData) => {
  const response = await fetch(`${API_BASE_URL}/api/v1/agents/${userId}/proxy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${agentSecretKey}`
    },
    body: JSON.stringify({
      ...requestData,
      stream: true
    })
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value)
    const lines = chunk.split('\n')
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') return
        
        try {
          const parsed = JSON.parse(data)
          console.log('Streaming chunk:', parsed)
        } catch (e) {
          // Игнорируем некорректные JSON
        }
      }
    }
  }
}
```

## 📊 Мониторинг и метрики

### Получение метрик Prometheus

```javascript
const getMetrics = async () => {
  const response = await fetch(`${API_BASE_URL}/metrics`)
  return response.text()
}
```

### Отслеживание запросов

Каждый запрос получает уникальный `request_id` в заголовках ответа:

```javascript
const makeTrackedRequest = async (endpoint, options = {}) => {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers
    }
  })

  const requestId = response.headers.get('X-Request-ID')
  console.log(`Request ID: ${requestId}`)

  return response.json()
}
```

## ⚡ Rate Limiting

### Обработка ограничений скорости

```javascript
const handleRateLimit = async (requestFn) => {
  try {
    return await requestFn()
  } catch (error) {
    if (error.status === 429) {
      const retryAfter = error.headers.get('Retry-After')
      console.log(`Rate limited. Retry after ${retryAfter} seconds`)
      
      // Ждем и повторяем запрос
      await new Promise(resolve => setTimeout(resolve, retryAfter * 1000))
      return await requestFn()
    }
    throw error
  }
}
```

### Проверка лимитов

```javascript
const checkRateLimit = (response) => {
  const remaining = response.headers.get('X-RateLimit-Remaining')
  const reset = response.headers.get('X-RateLimit-Reset')
  
  console.log(`Rate limit: ${remaining} requests remaining, resets at ${reset}`)
}
```

## 🛠️ Утилиты и хелперы

### Универсальный API клиент

```javascript
class APIClient {
  constructor(baseURL, getToken) {
    this.baseURL = baseURL
    this.getToken = getToken
  }

  async request(endpoint, options = {}) {
    const token = await this.getToken()
    
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
      }
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      throw new Error(error.message || `HTTP ${response.status}`)
    }

    return response.json()
  }

  // GET запрос
  async get(endpoint, params = {}) {
    const url = new URL(`${this.baseURL}${endpoint}`)
    Object.keys(params).forEach(key => url.searchParams.append(key, params[key]))
    
    return this.request(url.pathname + url.search)
  }

  // POST запрос
  async post(endpoint, data) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  // PUT запрос
  async put(endpoint, data) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  // DELETE запрос
  async delete(endpoint) {
    return this.request(endpoint, {
      method: 'DELETE'
    })
  }
}

// Использование
const apiClient = new APIClient(
  'https://betaback-production.up.railway.app',
  async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token
  }
)
```

### Обработка ошибок

```javascript
const handleAPIError = (error) => {
  if (error.message.includes('401')) {
    // Неавторизован - перенаправляем на логин
    window.location.href = '/login'
  } else if (error.message.includes('403')) {
    // Нет прав доступа
    showNotification('У вас нет прав для выполнения этого действия', 'error')
  } else if (error.message.includes('429')) {
    // Превышен лимит запросов
    showNotification('Слишком много запросов. Попробуйте позже.', 'warning')
  } else if (error.message.includes('500')) {
    // Ошибка сервера
    showNotification('Временная ошибка сервера. Попробуйте позже.', 'error')
  } else {
    // Общая ошибка
    showNotification(error.message || 'Произошла ошибка', 'error')
  }
}
```

### Кэширование

```javascript
class APICache {
  constructor(ttl = 300000) { // 5 минут по умолчанию
    this.cache = new Map()
    this.ttl = ttl
  }

  get(key) {
    const item = this.cache.get(key)
    if (!item) return null

    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key)
      return null
    }

    return item.data
  }

  set(key, data) {
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    })
  }

  clear() {
    this.cache.clear()
  }
}

const cache = new APICache()

const cachedRequest = async (key, requestFn) => {
  const cached = cache.get(key)
  if (cached) return cached

  const data = await requestFn()
  cache.set(key, data)
  return data
}
```

## 🎯 Примеры интеграции

### React Hook для работы с агентами

```javascript
import { useState, useEffect } from 'react'

const useAgents = () => {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchAgents = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const data = await apiClient.get('/api/v1/letta/agents')
      setAgents(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = async (agentId, message) => {
    try {
      return await apiClient.post(`/api/v1/letta/agents/${agentId}/messages`, {
        message
      })
    } catch (err) {
      setError(err.message)
      throw err
    }
  }

  useEffect(() => {
    fetchAgents()
  }, [])

  return {
    agents,
    loading,
    error,
    fetchAgents,
    sendMessage
  }
}
```

### Vue Composable для работы с API

```javascript
import { ref, computed } from 'vue'

export const useAPI = () => {
  const loading = ref(false)
  const error = ref(null)

  const request = async (endpoint, options = {}) => {
    loading.value = true
    error.value = null

    try {
      const result = await apiClient.request(endpoint, options)
      return result
    } catch (err) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  const isError = computed(() => !!error.value)

  return {
    loading,
    error,
    isError,
    request
  }
}
```

## 🔧 Конфигурация и настройка

### Переменные окружения

```javascript
// .env
REACT_APP_API_BASE_URL=https://betaback-production.up.railway.app
REACT_APP_SUPABASE_URL=https://your-project.supabase.co
REACT_APP_SUPABASE_ANON_KEY=your-anon-key
```

### Конфигурация для разных окружений

```javascript
const config = {
  development: {
    apiBaseURL: 'http://localhost:8000',
    supabaseURL: 'https://dev-project.supabase.co'
  },
  staging: {
    apiBaseURL: 'https://staging-api.example.com',
    supabaseURL: 'https://staging-project.supabase.co'
  },
  production: {
    apiBaseURL: 'https://betaback-production.up.railway.app',
    supabaseURL: 'https://prod-project.supabase.co'
  }
}

const env = process.env.NODE_ENV || 'development'
export const API_CONFIG = config[env]
```

## 📱 Рекомендации по UX/UI

### Индикаторы загрузки

```javascript
const LoadingSpinner = ({ size = 'medium' }) => {
  const sizeClasses = {
    small: 'w-4 h-4',
    medium: 'w-8 h-8',
    large: 'w-12 h-12'
  }

  return (
    <div className={`animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 ${sizeClasses[size]}`} />
  )
}
```

### Обработка состояний агентов

```javascript
const AgentStatus = ({ status }) => {
  const statusConfig = {
    active: { color: 'green', text: 'Активен' },
    inactive: { color: 'gray', text: 'Неактивен' },
    error: { color: 'red', text: 'Ошибка' },
    loading: { color: 'yellow', text: 'Загрузка' }
  }

  const config = statusConfig[status] || statusConfig.inactive

  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-${config.color}-100 text-${config.color}-800`}>
      <div className={`w-2 h-2 bg-${config.color}-400 rounded-full mr-1`} />
      {config.text}
    </span>
  )
}
```

### Компонент чата с агентом

```javascript
const AgentChat = ({ agentId }) => {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const sendMessage = async () => {
    if (!input.trim()) return

    const userMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await apiClient.post(`/api/v1/letta/agents/${agentId}/messages`, {
        message: input
      })
      
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.content
      }])
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'error',
        content: 'Произошла ошибка при отправке сообщения'
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-96 border rounded-lg">
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.map((message, index) => (
          <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xs px-3 py-2 rounded-lg ${
              message.role === 'user' 
                ? 'bg-blue-500 text-white' 
                : message.role === 'error'
                ? 'bg-red-100 text-red-800'
                : 'bg-gray-100 text-gray-800'
            }`}>
              {message.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-3 py-2 rounded-lg">
              <LoadingSpinner size="small" />
            </div>
          </div>
        )}
      </div>
      <div className="border-t p-4">
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Введите сообщение..."
            className="flex-1 border rounded-lg px-3 py-2"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-blue-500 text-white px-4 py-2 rounded-lg disabled:opacity-50"
          >
            Отправить
          </button>
        </div>
      </div>
    </div>
  )
}
```

## 🚨 Обработка ошибок и отладка

### Логирование запросов

```javascript
const debugRequest = async (endpoint, options = {}) => {
  console.log('🚀 Request:', { endpoint, options })
  
  const startTime = Date.now()
  try {
    const response = await apiClient.request(endpoint, options)
    const duration = Date.now() - startTime
    
    console.log('✅ Response:', { 
      duration: `${duration}ms`,
      data: response 
    })
    
    return response
  } catch (error) {
    const duration = Date.now() - startTime
    
    console.error('❌ Error:', { 
      duration: `${duration}ms`,
      error: error.message 
    })
    
    throw error
  }
}
```

### Проверка CORS

```javascript
const checkCORS = async () => {
  try {
    const response = await fetch('https://betaback-production.up.railway.app/health', {
      method: 'OPTIONS',
      headers: {
        'Origin': window.location.origin,
        'Access-Control-Request-Method': 'GET'
      }
    })
    
    console.log('CORS check:', {
      status: response.status,
      headers: Object.fromEntries(response.headers.entries())
    })
  } catch (error) {
    console.error('CORS error:', error)
  }
}
```

## 📚 Дополнительные ресурсы

### Полезные ссылки

- [Letta API Documentation](https://docs.letta.com/api-reference/overview)
- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### SDK и библиотеки

```bash
# Установка зависимостей
npm install @supabase/supabase-js
npm install @letta-ai/letta-client  # TypeScript SDK для Letta

# Или для Python
pip install letta-client
```

### Примеры проектов

- [Letta Examples](https://github.com/letta-ai/letta-examples)
- [Supabase Examples](https://github.com/supabase/supabase/tree/master/examples)

---

**Версия документации:** 1.0.0  
**Последнее обновление:** 21 января 2025  
**API версия:** 1.0.0

Для получения дополнительной помощи обращайтесь к команде разработки или создавайте issues в репозитории проекта.
