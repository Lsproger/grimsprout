# Обработка edge-cases: LLM и git

**Фаза**: 4
**Статус**: backlog
**Приоритет**: medium
**Зависимости**: phase3-001-ollama-client, phase3-003-action-dispatch

## Описание

Бот должен корректно обрабатывать деградированные состояния: когда LLM не возвращает валидный JSON после повторной попытки, и когда git-репозиторий заблокирован (lock-файл занят).

## Критерии готовности

- [ ] LLM не вернула JSON: после N повторных запросов (`RETRY_MSG`) бот отвечает user-friendly сообщением без traceback
- [ ] Git lock timeout: `DirtyRepoError` / `git.exc.GitCommandError` на `index.lock` → сообщение «репозиторий занят, попробуй через несколько секунд»
- [ ] Все edge-case пути покрыты unit-тестами
- [ ] Нет `Internal Server Error` в логах при штатных сбоях LLM/git

## Заметки

- `DirtyRepoError` уже определён в `utils/errors.py`, часть обработки уже есть в `actions.py` и `llm_router.py`
- Проверить: что происходит при `git.index.lock` во время параллельных операций
- Рассмотреть экспоненциальный backoff или блокировку через asyncio.Lock для git-операций
