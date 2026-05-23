# Phase 3D: Тип действия "query" в LLM-схеме

**Фаза**: 3
**Статус**: backlog
**Приоритет**: high
**Зависимости**: phase3-002, phase3-003

## Описание

LLM-схема не содержит типа для информационных запросов («какие растения есть?», «когда поливалась калатея?»). В результате LLM вынуждена присваивать им `action: "observe"` с высоким confidence, что:
1. Тратит 7+ секунд на запрос, который решается локально.
2. Приводит к попытке применить действие к растению там, где пользователь просто спросил.

**Примеры запросов, которые должны попасть в `"query"`:**
- «какие у меня есть растения?»
- «когда поливалась калатея?»
- «сколько у меня горшков?»
- «что такое здоровье растения?»

## Решение

### 1. Схема: добавить `"query"` в `action` enum

Файл `config/prompts/intent_schema.json`:
```json
"action": {
  "type": "string",
  "enum": ["water", "fertilize", "repot", "observe", "create", "query", "unknown"]
}
```

Поле `clarification` при `action: "query"` используется как **ответ** LLM на вопрос пользователя (не запрос уточнения).

### 2. Системный промпт: инструкция для `"query"`

В `config/prompts/system_undertaker.md` добавить секцию:
```
Если сообщение — информационный вопрос (а не действие с растением),
используй action: "query" и помести ответ в поле `clarification`.
```

### 3. Router: обработать `action == "query"`

В `llm_router.handle_free_text`, добавить ветку **до** блока resolve_plant:
```python
if intent.action == "query":
    reply = intent.clarification or "Не знаю ответа. Попробуй /plants или /help."
    await message.answer(reply)
    return
```

### 4. Pre-filter для частых вопросов (опционально, Phase 4)

Ряд вопросов можно закорачивать ещё до LLM:
- «какие растения» / «список» → ответить списком из `plant_repo.list_plants()`
- «помощь» / «help» → перенаправить на `/help`

Это снизит latency с ~7с до ~0с для частых FAQ. Реализовать как отдельный шаг в `handle_free_text` перед `_build_messages`.

## Критерии готовности
- [ ] `"query"` добавлен в `intent_schema.json` и в `Intent.action` (pydantic enum)
- [ ] Системный промпт содержит инструкцию для `"query"` / `clarification`-как-ответ
- [ ] `handle_free_text` возвращает `intent.clarification` при `action == "query"` без обращения к git
- [ ] Ручной тест: «какие у меня растения?» → ответ без git-commit, без задержки на resolve_plant

## Заметки
- `clarification` сейчас двусмысленно: означает и «LLM просит уточнить», и (после этого таска) «LLM отвечает на вопрос». Рассмотреть переименование в `response_text` в будущей версии схемы.
- Если LLM возвращает `action: "observe"` + `confidence >= 0.5` + `target_file: null` — это потенциально тот же паттерн (вопрос без объекта). Добавить guard в dispatch: `observe` без `plant_id` → message «Выбери растение через /plants», не пытаться делать commit.
