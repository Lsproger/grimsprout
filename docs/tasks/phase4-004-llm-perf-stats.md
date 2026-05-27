# LLM Performance Stats

**Фаза**: 4
**Статус**: done
**Приоритет**: low
**Зависимости**: phase3-001-ollama-client

## Описание

Логировать метрики производительности LLM (`tokens_per_sec`, `eval_count`) в INFO-лог. Опциональный флаг `llm.show_perf_stats` добавляет футер `⚡ N tok/s · M tok` к ответам бота в Telegram.

## Критерии готовности

- [x] `LLMStats` dataclass в `ollama_client.py` (поля: `tokens_per_sec`, `eval_count`, `prompt_eval_count`)
- [x] `chat()` возвращает `tuple[dict, LLMStats]`
- [x] `llm.show_perf_stats: bool = False` в `LLMConfig` (`config.py`)
- [x] `llm_router.py` логирует `tokens_per_sec` / `eval_count` через loguru INFO
- [x] При `show_perf_stats=True` к ответу бота добавляется футер `⚡ N tok/s · M tok`

## Заметки

- Реализовано в `src/grimsprout/services/llm/ollama_client.py` и `src/grimsprout/bot/handlers/llm_router.py`
- Не требует изменений схемы БД
