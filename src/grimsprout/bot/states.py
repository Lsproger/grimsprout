"""FSM states: NewCardFSM, RegressionFSM. TODO(phase-4)."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class NewCardFSM(StatesGroup):
    common_name = State()
    botanical_name = State()
    variety = State()
    purchase_date = State()
    purchase_location = State()
    age_group = State()
    confirm = State()


class RegressionFSM(StatesGroup):
    waiting_for_input = State()
