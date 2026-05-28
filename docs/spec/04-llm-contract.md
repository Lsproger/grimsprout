# 04 — Контракт с LLM

> Этот документ описывает архитектуру **Фазы 4.5** (tool calling).  
> Предыдущий подход (JSON-интент) задокументирован в ADR 0004 (устарел; см. ADR 0007).

## 4.1. Два агента

GrimSprout использует два агента, оба через `ollama.AsyncClient`:

| Агент | Конфиг | Роль |
|---|---|---|
| **Classifier** | `llm.effective_classifier_model` | Получает текст пользователя, вызывает tool calls для действий |
| **Assistant** | `llm.effective_assistant_model` | Отвечает на свободные вопросы без инструментов |

`effective_*_model` — свойство `LLMConfig`: возвращает `classifier_model` / `assistant_model`, если непусто, иначе `model`.

Оба агента получают одинаковый `{repo_summary}` в системном промпте (см. §4.3).

## 4.2. Инструменты (tool calls)

Инструменты передаются Classifier в параметре `tools` стандартного формата OpenAI.  
Определены в `src/grimsprout/services/llm/tools.py`.

| Инструмент | Тип | Обязательные аргументы | Опциональные |
|---|---|---|---|
| `water` | mutating | `plant_ids: list[str]` | — |
| `fertilize` | mutating | `plant_ids: list[str]` | — |
| `repot` | mutating | `plant_ids: list[str]` | — |
| `observe` | mutating | `plant_id: str`, `note: str` | — |
| `get_plant_details` | read-only | `plant_id: str` | — |
| `create_plant` | read-only* | `common_name: str` | `botanical_name: str` |

**Батч-поддержка:** `plant_ids=["all"]` означает «все растения в коллекции».  
`MUTATING_TOOLS = frozenset({"water", "fertilize", "repot", "observe"})` — используется агентом при разделении на read-only / mutating.

*`create_plant` read-only в смысле агента: реальное создание карточки происходит через FSM-команду `/new`. Tool executor возвращает подсказку.

## 4.3. Repo Summary

Перед каждым вызовом Classifier формируется сводка коллекции:

```python
repo_summary = build_repo_summary(repo_path)
```

Формат вывода:
```
Коллекция (3 растения):
- areca_01 "Арека" alive h=7
  2026-05-28: Полив выполнен
- calathea_01 "Калатея" alive h=6
  2026-05-10: Подкормка
- paporotnik_02 "Папоротник" alive h=8
```

Сводка подставляется в шаблон системного промпта через `{repo_summary}`.  
Пересчитывается при каждом запросе — кеширование не применяется.

## 4.4. Агентный цикл (`agent.run()`)

```
1. build_repo_summary(repo_path)
2. chat_with_tools(classifier_model, classifier_msgs, TOOL_DEFS)
   ├─ tool_calls == [] AND content непуст  → вернуть AgentResult(content)
   ├─ tool_calls == [] AND content пуст    → chat(assistant_model, assistant_msgs) → AgentResult
   ├─ только read-only tools               → execute_tool() × N → feed results back
   │                                         → chat(classifier_model, follow_up_msgs) → AgentResult
   └─ есть mutating tools
         ├─ confirm_commits=true  → AgentResult(needs_confirmation=True, pending_mutations=[...])
         └─ confirm_commits=false → execute_tool() × N → AgentResult(outputs joined)
```

Read-only tools выполняются немедленно; их результат добавляется в контекст как `{"role": "tool", "content": ...}`, после чего Classifier формирует финальный ответ.

## 4.5. Подтверждение мутаций

При `confirm_commits=true` агент возвращает `AgentResult` с `needs_confirmation=True`.  
Bot handler (`llm_router.py`) сохраняет `pending_mutations` в FSM-состоянии:

```python
# Сериализация в FSM:
[{"tool_name": m.tool_name, "args": m.args} for m in result.pending_mutations]

# Десериализация:
[PendingMutation(tool_name=m["tool_name"], args=m["args"]) for m in raw]
```

После подтверждения пользователем вызывается `agent.execute_pending(pending, ...)`.

Превью перед подтверждением (строится `_build_pending_preview()`):
```
⏳ Подтвердить действия?
🌿 water: <code>areca_01</code>, <code>calathea_01</code>
🌿 observe: <code>paporotnik_02</code>
  "Листья пожелтели по краям"
```

## 4.6. Assistant — свободные вопросы

Если Classifier не вернул tool calls и content пуст, запрос перенаправляется Assistant.  
Assistant получает `system_assistant.md` с `{repo_summary}` и отвечает на свободные вопросы о растениях, уходе, статусах.

Assistant **не** получает инструменты и **не** вызывает мутации.

## 4.7. Метрики производительности (`LLMStats`)

`ollama.AsyncClient.chat()` возвращает `ChatResponse`; `_extract_stats()` извлекает:

| Поле `LLMStats` | Источник (`ChatResponse`) | Описание |
|---|---|---|
| `tokens_per_sec` | `eval_count / eval_duration × 10⁹` | Скорость генерации, tok/s |
| `eval_count` | `resp.eval_count` | Сгенерировано токенов |
| `prompt_eval_count` | `resp.prompt_eval_count` | Токенов промпта |
| `total_duration_ms` | `resp.total_duration / 10⁶` | Полное время, мс |

Все поля — `None`, если Ollama не вернула значение. Статистика логируется на уровне INFO.  
При `llm.show_perf_stats=true` к ответам добавляется: `⚡ 42 tok/s · 38 tok`

