# phase45-001 — Миграция на tool calling (Фаза 4.5)

**Статус:** done  
**Фаза:** 4.5  
**Зависимости:** phase4-004 (LLM perf stats)

## Цель

Заменить ручной JSON-интент на нативный tool calling через `python-ollama`.  
Исправить три ключевые проблемы архитектуры Фазы 3:

1. **«Слепота» к растениям** — LLM не видела список карточек, изобретала ID.
2. **Не явные намерения** — «Полил арека» требовало скрытого парсинга JSON.
3. **Одна модель на всё** — нет разделения router / assistant.

## Решение

Разбить LLM-слой на два агента:

| Агент | Модель | Роль |
|---|---|---|
| **Classifier** | `effective_classifier_model` | Маршрутизация через 6 tool calls |
| **Assistant** | `effective_assistant_model` | Свободные ответы на вопросы |

Каждый вызов агента получает `build_repo_summary()` — свежую сводку коллекции.

## Реализованные изменения

### Зависимости
- `requirements.txt`: добавлен `ollama>=0.3`, удалён `httpx`-only путь

### Конфиг (`LLMConfig`)
- `classifier_model: str` — пустая строка → fallback к `model`
- `assistant_model: str` — пустая строка → fallback к `model`
- `classifier_prompt_file: Path | None`
- `assistant_prompt_file: Path | None`
- `system_prompt_file`, `intent_schema_file` стали `Optional` для обратной совместимости
- Свойства `effective_classifier_model`, `effective_assistant_model`

### Новые файлы
| Файл | Назначение |
|---|---|
| `services/llm/ollama_client.py` | Перезаписан: `chat()` и `chat_with_tools()` через `ollama.AsyncClient` |
| `services/llm/tools.py` | `TOOL_DEFS` — 6 инструментов; `MUTATING_TOOLS` frozenset |
| `services/llm/tool_executor.py` | Диспатчер: `execute_tool(name, args, ...)` |
| `services/llm/tool_call.py` | `PendingMutation`, `AgentResult` dataclasses |
| `services/llm/agent.py` | `run()` — полный цикл агента; `execute_pending()` |
| `core/plant_repo.py` | `build_repo_summary()`, `_extract_changelog_entries()` |
| `config/prompts/system_classifier.md` | Системный промпт для Classifier |
| `config/prompts/system_assistant.md` | Системный промпт для Assistant |

### Изменённые файлы
| Файл | Изменения |
|---|---|
| `bot/handlers/llm_router.py` | Полная перепись: FSM хранит `pending_mutations` вместо `intent_data` |
| `config.py` | `LLMConfig` расширен (см. выше) |
| `config/config.yaml` | Добавлены `classifier_model`, `assistant_model`, пути к промптам |
| `config/config.example.yaml` | Документированы все новые поля |

### Устаревшие файлы (сохранены как справка)
| Файл | Статус |
|---|---|
| `services/llm/intent_parser.py` | Deprecated — не используется в Фазе 4.5 |
| `config/prompts/system_undertaker.md` | Deprecated — заменён classifier/assistant промптами |
| `config/prompts/intent_schema.json` | Deprecated — схема больше не нужна |

## Инструменты (tool_defs)

| Инструмент | Тип | Аргументы |
|---|---|---|
| `water` | mutating | `plant_ids: list[str]` — `["all"]` для всей коллекции |
| `fertilize` | mutating | `plant_ids: list[str]` |
| `repot` | mutating | `plant_ids: list[str]` |
| `observe` | mutating | `plant_id: str`, `note: str` |
| `get_plant_details` | read-only | `plant_id: str` |
| `create_plant` | read-only* | `common_name: str`, `botanical_name?: str` |

*`create_plant` возвращает подсказку `/new` — реальное создание через FSM.

## Агентный цикл

```
Classifier(tool-calls) 
  ├─ tool_calls == [] + content → вернуть ответ напрямую
  ├─ tool_calls == [] + no content → Assistant(free-text) → ответ
  ├─ read-only tools → execute_tool() → feed back → Classifier → ответ
  └─ mutating tools
        ├─ confirm_commits=true → AgentResult(needs_confirmation=True, pending_mutations)
        └─ confirm_commits=false → execute_tool() сразу → ответ
```

## Тесты

Добавлены/переписаны:
- `tests/unit/test_ollama_client.py` — мок `ollama.AsyncClient` вместо httpx
- `tests/unit/test_agent.py` — все ветви `run()`, `execute_pending`, `_build_pending_preview`
- `tests/unit/test_tool_executor.py` — диспатч, `_resolve_plant_ids`, read-only/mutating
- `tests/unit/test_plant_repo.py` — `test_build_repo_summary_*`
- `tests/unit/test_llm_router.py` — обновлены под новый API

**Итог:** 149 тестов, все проходят. Lint: ruff check + format — 0 ошибок.
