# Phase 3A: Ollama Client

**Фаза**: 3
**Статус**: done
**Приоритет**: high
**Зависимости**: нет
**Блокирует**: phase3-002, phase3-003

## Описание

Реализовать async HTTP-клиент для Ollama API (`POST /api/chat` с `format: "json"`).
Сигнатура уже определена в `src/grimsprout/services/llm/ollama_client.py` — нужно заменить `raise NotImplementedError` на рабочую реализацию.

## Требования

### Реализация `chat()`
```
POST {base_url}/api/chat
Body: {model, messages, format: "json", stream: false, options: {temperature}}
Response: {message: {content: "<json string>"}} → parse content → return dict
```

- Использовать `httpx.AsyncClient` (уже в requirements.txt)
- `timeout` из конфига (default 30s)
- При HTTP-ошибке → `LLMResponseError` (уже определён в `utils/errors.py`)
- При таймауте → `LLMResponseError("Ollama timeout")`
- При невалидном JSON в `message.content` → `LLMResponseError("invalid JSON from LLM")`
- Логировать: model, длительность запроса, размер ответа (loguru)

### Тесты — `tests/unit/test_ollama_client.py`
- Mock httpx (respx или monkeypatch)
- Кейсы: успешный ответ, таймаут, HTTP 500, невалидный JSON в content, пустой ответ

## Критерии готовности
- [ ] `ollama_client.chat()` возвращает dict при успешном ответе
- [ ] Raise `LLMResponseError` при таймауте / HTTP-ошибке / невалидном JSON
- [ ] Логируется model + duration
- [ ] Unit-тесты проходят
- [ ] `make check` зелёный

## Файлы
- `src/grimsprout/services/llm/ollama_client.py` — реализация
- `src/grimsprout/services/llm/__init__.py` — экспорт `chat`
- `tests/unit/test_ollama_client.py` — тесты
- `src/grimsprout/utils/errors.py` — `LLMResponseError` (уже есть)

## Заметки

### Формат запроса Ollama
```json
{
  "model": "gemma3:4b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "полил калатею"}
  ],
  "format": "json",
  "stream": false,
  "options": {"temperature": 0.1}
}
```

### Формат ответа Ollama
```json
{
  "message": {
    "role": "assistant",
    "content": "{\"action\": \"water\", \"target_file\": \"calathea_01\", ...}"
  },
  "done": true,
  "total_duration": 1234567890
}
```
