# Gemini Bridge: применение изменений

**Фаза**: 5
**Статус**: backlog
**Приоритет**: medium
**Зависимости**: phase5-001-gemini-payload-intake, phase3-003-action-dispatch, phase3-005-llm-confirm-gate

## Описание

Применить операции, полученные от Gemini-парсера, через существующий Action dispatch. Перед записью запросить подтверждение через confirm gate.

**Кто**: editor+

**Что**: Список операций из `phase5-001` передаётся в диспетчер действий (Фаза 3); каждая мутация проходит через confirm gate; результат фиксируется git-коммитом.

## Критерии готовности

- [ ] Операции типа «обновление YAML-поля» → `md_parser.update_yaml` + git commit
- [ ] Операции типа «запись в changelog» → `changelog.append` + git commit
- [ ] Batch-операции: одно подтверждение для всего набора с предпросмотром изменений
- [ ] Audit-запись с `action=gemini_apply`
- [ ] Интеграционный тест: payload → confirm → commit

## Заметки

- Переиспользовать `ActionConfirmFSM` из `bot/states.py`
- Предпросмотр для batch: показывать все изменения одним сообщением до подтверждения
- `action=gemini_apply` должен логировать source (gemini) для отличия от LLM-action
