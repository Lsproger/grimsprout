# Phase 3F: Порог confidence для мутирующих действий LLM

**Фаза**: 3
**Статус**: done
**Приоритет**: medium
**Зависимости**: phase3-002, phase3-004

## Описание

Текущий порог `confidence < 0.5` одинаков для всех action-типов: информационных (`query`, `observe`) и мутирующих (`water`, `fertilize`, `repot`). Это слишком мягко для операций, которые пишут в git:

- `confidence = 0.6` при `action: "water"` → коммит происходит без вопросов
- LLM вернула `observe` с `confidence = 0.9` на вопрос «какие растения?» — схема позволяет это

## Решение

Ввести **два порога** в `RepositoryConfig` (или `LLMConfig`):

```yaml
llm:
  confidence_threshold: 0.5       # для query/observe (читающие)
  mutate_confidence_threshold: 0.8 # для water/fertilize/repot (пишущие в git)
```

В `handle_free_text`:
```python
MUTATING_ACTIONS = {"water", "fertilize", "repot"}

threshold = (
    cfg.llm.mutate_confidence_threshold
    if intent.action in MUTATING_ACTIONS
    else cfg.llm.confidence_threshold
)
if intent.confidence < threshold or intent.clarification:
    reply = intent.clarification or "Не совсем понял. Уточни, что именно нужно сделать."
    await message.answer(reply)
    return
```

## Критерии готовности
- [ ] `LLMConfig` содержит `confidence_threshold` и `mutate_confidence_threshold`
- [ ] `config.yaml` / `config.example.yaml` обновлены с новыми полями
- [ ] `handle_free_text` использует правильный порог в зависимости от action
- [ ] Unit-тест: `water` с `confidence=0.6` → уточняющий вопрос, не коммит
- [ ] `make check` зелёный

## Заметки
- Рекомендуемые значения по умолчанию: `confidence_threshold: 0.5`, `mutate_confidence_threshold: 0.75`
- `observe` — пограничный: пишет в changelog/git, но менее критичен чем полив. Пока считать **не-мутирующим** (threshold=0.5), пересмотреть после накопления опыта.
- Этот таск имеет смысл после phase3-004: если `"query"` добавлен, LLM перестанет возвращать `observe` на информационные вопросы — и false-positive commits уменьшатся естественно.
