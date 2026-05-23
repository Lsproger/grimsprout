"""FSM states: NewCardFSM, EditFSM, ActionConfirmFSM, RegressionFSM."""

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


class EditFSM(StatesGroup):
    choosing_field = State()
    entering_value = State()


class ActionConfirmFSM(StatesGroup):
    waiting = State()
    waiting_llm = State()


class RegressionFSM(StatesGroup):
    waiting_for_input = State()
