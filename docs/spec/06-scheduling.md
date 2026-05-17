# 06 — Расписания и регрессия

## 6.1. Хранилище
Коллекция `schedules` (см. [02-data-model.md](02-data-model.md)). APScheduler с MongoDB jobstore.

## 6.2. Создание/обновление
- `/schedule <plant_id|common_name> <kind> <Nd>` — `kind` ∈ `water|fertilize|repot`, `N` — целое число дней.
- При создании `next_run_at = now() + interval_days`.
- При повторе команды для той же тройки `(plant_id, kind, owner_tg_id)` — апдейт документа (upsert).

## 6.3. Тип задачи и оповещение
- Каждое срабатывание шлёт в Telegram сообщение с inline-кнопками:
  - **Полил/Удобрил/Пересадил** — выполняет соответствующее действие над файлом (как `/water` и пр.) + сдвигает `next_run_at += interval_days`.
  - **Отложить** — `next_run_at += 1d` (или модальный выбор: 1д/3д/неделя).
  - **Отменить** — `active = false`.
  - **Регрессия** — переход в FSM регрессии.

## 6.4. Регрессия
- Бот переходит в состояние `RegressionFSM(schedule_id)`.
- Ждёт текст и/или фото от пользователя.
- LLM получает контекст «регрессия по {kind} для {plant_id}». Ответ — обычный JSON-интент + опциональный `reschedule_days`.
- Бот применяет действия (фото в `images/`, запись в changelog, обновление YAML) и сдвигает `next_run_at += reschedule_days || interval_days`.
- В `audit_log` пишется `action=regression`.

## 6.5. Часовой пояс
- Глобальный, из `config.yaml` (`scheduling.timezone`, по умолчанию `Europe/Warsaw`).
- Хранение `next_run_at` — в UTC; конвертация при показе пользователю.
