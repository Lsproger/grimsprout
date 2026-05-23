"""Inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Field display names for /edit keyboard (ordered)
_EDIT_FIELDS: list[tuple[str, str]] = [
    ("status", "Статус"),
    ("health_score", "Здоровье"),
    ("common_name", "Название"),
    ("botanical_name", "Научное"),
    ("age_group", "Возраст"),
    ("pot_size_cm", "Горшок (см)"),
    ("pot_type", "Тип горшка"),
    ("light_req", "Освещение"),
    ("soil_type", "Грунт"),
    ("humidity_req", "Влажность"),
    ("purchase_location", "Откуда"),
    ("tags", "Теги"),
]

_ENUM_VALUES: dict[str, list[str]] = {
    "status": ["alive", "dead", "sold", "gifted"],
    "pot_type": ["plastic", "terracotta", "ceramic", "self-watering"],
    "age_group": ["seedling", "juvenile", "adult"],
}


def plants_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in items:
        label = f"{p.get('common_name') or p['id']} · {p['id']}"
        kb.button(text=label[:60], callback_data=f"plant:set:{p['id']}")
        kb.button(text="ℹ️", callback_data=f"plant:info:{p['id']}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="action:confirm")
    kb.button(text="❌ Отменить", callback_data="action:cancel")
    kb.adjust(2)
    return kb.as_markup()


def field_selection_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for field, label in _EDIT_FIELDS:
        kb.button(text=label, callback_data=f"edit:field:{field}")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(2)
    return kb.as_markup()


def enum_value_keyboard(field: str) -> InlineKeyboardMarkup | None:
    values = _ENUM_VALUES.get(field)
    if not values:
        return None
    kb = InlineKeyboardBuilder()
    for v in values:
        kb.button(text=v, callback_data=f"edit:value:{v}")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(2)
    return kb.as_markup()
