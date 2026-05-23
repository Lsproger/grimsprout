"""Inline keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def plants_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in items:
        label = f"{p.get('common_name') or p['id']} · {p['id']}"
        kb.button(text=label[:60], callback_data=f"plant:set:{p['id']}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="action:confirm")
    kb.button(text="❌ Отменить", callback_data="action:cancel")
    kb.adjust(2)
    return kb.as_markup()
