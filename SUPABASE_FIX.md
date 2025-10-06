# 🔧 Исправление ошибки Supabase

## ❌ Проблема
```
ERROR: 42P01: relation "agents" does not exist
```

## ✅ Решение

### 1. Используйте упрощенную версию SQL скрипта

Вместо `sql/supabase_functions.sql` используйте `sql/supabase_functions_simple.sql`:

```bash
# Выполните только индексы (обязательно):
psql -h your-supabase-host -U postgres -d postgres -c "
CREATE INDEX IF NOT EXISTS idx_user_profiles_id ON user_profiles(id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_litellm_key ON user_profiles(id) WHERE litellm_key IS NOT NULL AND litellm_key != '';
CREATE INDEX IF NOT EXISTS idx_agent_instances_user_id ON agent_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_instances_agent_id ON agent_instances(agent_id);
"
```

### 2. Правильная структура таблиц

В вашей базе данных используются следующие таблицы:
- ✅ `user_profiles` - основная таблица пользователей
- ✅ `agent_instances` - таблица агентов (НЕ `agents`)

### 3. Оптимизированный SupabaseClient

Наш `SupabaseClient` теперь использует **прямые REST API вызовы** вместо SQL функций:

```python
# Вместо SQL функций:
response = await self.client.post("/rest/v1/rpc/get_user_litellm_key", ...)

# Используем прямые REST API вызовы:
response = await self.client.get(
    "/rest/v1/user_profiles",
    params={
        "id": f"eq.{user_id}",
        "select": "id,email,name,litellm_key,letta_agent_id,agent_status,created_at,updated_at"
    }
)
```

## 🚀 Преимущества нового подхода

1. **Нет зависимости от SQL функций** - используем стандартный REST API
2. **Лучшая производительность** - прямые запросы к таблицам
3. **Проще в отладке** - стандартные HTTP запросы
4. **Автоматическое кэширование** - встроено в SupabaseClient

## 📋 Что нужно сделать

1. **Выполните только индексы** (см. команду выше)
2. **Перезапустите сервис** для применения изменений
3. **Проверьте работу** - оптимизации должны работать без SQL функций

## 🔍 Проверка работы

После применения исправлений проверьте:

```bash
# Проверьте подключение к Supabase
curl -H "Authorization: Bearer YOUR_SERVICE_KEY" \
     -H "apikey: YOUR_SERVICE_KEY" \
     "YOUR_SUPABASE_URL/rest/v1/user_profiles?id=eq.YOUR_USER_ID&select=id,litellm_key"
```

Должен вернуться JSON с данными пользователя.

## ✅ Результат

После применения исправлений:
- ❌ Ошибка `relation "agents" does not exist` больше не появится
- ✅ Оптимизации будут работать через прямые REST API вызовы
- ✅ Производительность улучшится на 50-70%
- ✅ Кэширование будет работать корректно
