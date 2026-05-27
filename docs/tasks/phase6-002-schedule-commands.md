# Команды /schedule и /snooze

**Фаза**: 6
**Статус**: backlog
**Приоритет**: high
**Зависимости**: phase6-001-scheduler-service

## Описание

Пользовательские команды для управления расписанием напоминаний о поливе, удобрении и пересадке.

**Кто**: editor+

**Что**: `/schedule` создаёт или обновляет задание; `/snooze` откладывает ближайшее напоминание на `default_snooze_days`.

## Сценарии использования

```
User: /schedule areca_01 water 7
Bot: ✅ Напоминание о поливе areca_01 — каждые 7 дней. Следующее: 2026-06-03

User: /snooze
Bot: ⏭ Напоминание отложено на 1 день. Следующее: 2026-05-29

User: /schedules
Bot: 📅 Активные расписания:
     • areca_01 — полив каждые 7 дней (след. 2026-06-03)
     • calathea_01 — удобрение каждые 14 дней (след. 2026-06-10)
```

## Критерии готовности

- [ ] `/schedule [plant_id] <kind> <interval_days>` — создаёт/обновляет задание (upsert)
- [ ] `/schedules` — список всех активных заданий пользователя
- [ ] `/snooze [plant_id] [kind]` — откладывает ближайшее напоминание на `default_snooze_days`
- [ ] Валидация: `kind` ∈ {water, fertilize, repot}; `interval_days` > 0
- [ ] Без аргумента `plant_id` — использовать `current_plant_id` из сессии
- [ ] Handler зарегистрирован в `bot/app.py`

## Заметки

- Stub уже в `src/grimsprout/bot/handlers/schedules.py`
- Inline-кнопки «Выполнено» и «Отложить» в напоминании реализуются как callback в том же handler
