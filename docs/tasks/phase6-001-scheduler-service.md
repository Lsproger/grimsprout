# Планировщик напоминаний: SchedulerService

**Фаза**: 6
**Статус**: backlog
**Приоритет**: high
**Зависимости**: phase4-001-new-card-command

## Описание

Реализовать `SchedulerService` на базе APScheduler с MongoDB jobstore. Сервис хранит задания в коллекции `schedules`, запускает напоминания о поливе/удобрении/пересадке в указанное время.

**Зачем**: Без планировщика пользователь не получает проактивных напоминаний и вынужден сам отслеживать графики ухода.

**Кто**: система (bot-side daemon)

**Что**: APScheduler с `AsyncIOScheduler`, jobstore → MongoDB, триггер `IntervalTrigger`. При срабатывании — отправка Telegram-сообщения через bot.

## Критерии готовности

- [ ] `SchedulerService` инициализируется при старте бота и подключается к MongoDB jobstore
- [ ] CRUD-операции: `add_job`, `remove_job`, `list_jobs`, `snooze_job` — через `SchedulesRepo`
- [ ] `SchedulesRepo` (stub уже в `db/repositories/schedules.py`) — полностью реализован
- [ ] При срабатывании: bot отправляет напоминание с inline-кнопками «Выполнено» / «Отложить»
- [ ] Graceful shutdown: планировщик останавливается при завершении бота
- [ ] Unit-тесты на CRUD-операции репозитория

## Заметки

- Стаб уже существует: `src/grimsprout/services/scheduler_service.py` и `src/grimsprout/bot/handlers/schedules.py` — содержат `TODO(phase-6)` (необходимо исправить в коде)
- APScheduler уже в `requirements.txt`? Проверить перед реализацией
- `SchedulingConfig` в `config.py` уже содержит `timezone` и `default_snooze_days`
