# 04 — Контракт с LLM

## 4.1. Провайдер
- Ollama, endpoint `POST {base_url}/api/chat`.
- Параметры запроса: `model`, `messages`, `format: "json"`, `options.temperature`.
- Таймаут — 30 секунд по умолчанию, конфигурируем.

## 4.2. Системный промпт (`config/prompts/system_undertaker.md`)
Стиль: профессиональный фитопатолог с тёмным юмором («гробовщик»). LLM ОБЯЗАНА вернуть только валидный JSON по схеме ниже, без преамбулы и комментариев. На русском.

## 4.3. JSON-схема ответа (`config/prompts/intent_schema.json`)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["action", "confidence"],
  "additionalProperties": false,
  "properties": {
    "target_file": { "type": ["string", "null"] },
    "action": {
      "type": "string",
      "enum": ["water", "fertilize", "repot", "observe", "create", "unknown"]
    },
    "health_delta": { "type": ["integer", "null"], "minimum": -3, "maximum": 3 },
    "tags_add": { "type": "array", "items": { "type": "string" } },
    "tags_remove": { "type": "array", "items": { "type": "string" } },
    "changelog_entry": { "type": ["string", "null"] },
    "needs_photo": { "type": "boolean" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "clarification": { "type": ["string", "null"] },
    "create_fields": {
      "type": ["object", "null"],
      "description": "Заполняется только при action=create; ключи — поля YAML.",
      "additionalProperties": true
    },
    "reschedule_days": {
      "type": ["integer", "null"],
      "description": "Используется в сценарии регрессии для сдвига расписания."
    }
  }
}
```

## 4.4. Сопоставление `target_file`
1. Точное совпадение `id` карточки.
2. Точное совпадение по имени файла без `.md`.
3. Fuzzy по `common_name` (rapidfuzz, threshold ≥ 80) — допустимо одно совпадение.
4. Иначе бот показывает inline-клавиатуру выбора из топ-N кандидатов.

## 4.5. Retry/fallback
- Невалидный JSON → один повтор с сообщением «верни строго JSON по схеме».
- При `confidence < 0.5` или `clarification != null` — бот задаёт уточняющий вопрос пользователю и НЕ применяет действия.
- При `action == "unknown"` — бот предлагает прямые команды.

## 4.6. Контекст запроса
В `messages` передаём:
1. `system` — содержимое `system_undertaker.md` + JSON-схема.
2. `user` — текст пользователя.
3. (Опционально) `system` с кратким списком известных id растений (для лучшего сопоставления `target_file`).
4. (Опционально) `system` с пометкой «контекст: регрессия по {kind}» для сценария регрессии.

Фото в LLM на MVP **не** передаются (multimodal — задача отдельного `PhotoAnalyzer`, который пока заглушка).
