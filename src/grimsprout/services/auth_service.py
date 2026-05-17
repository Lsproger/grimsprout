"""AuthService helpers: role rank, requires_role decorator."""
from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, Literal

from aiogram.types import CallbackQuery, Message

Role = Literal["admin", "editor", "publisher", "viewer"]

ROLE_RANK: dict[str, int] = {"viewer": 0, "editor": 1, "publisher": 2, "admin": 3}

VALID_ROLES: tuple[str, ...] = tuple(ROLE_RANK.keys())


def has_role(actual: Role | None, *required: Role) -> bool:
    if not actual:
        return False
    if not required:
        return True
    actual_rank = ROLE_RANK.get(actual, -1)
    return any(actual_rank >= ROLE_RANK[r] for r in required)


def requires_role(*required: Role) -> Callable:
    """Decorator for aiogram handlers. Expects `role` in handler kwargs (set by AuthMiddleware)."""

    def deco(
        handler: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapped(event: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
            role: Role | None = kwargs.get("role")
            if not has_role(role, *required):
                deny = "Недостаточно прав для этого ритуала."
                if isinstance(event, CallbackQuery):
                    await event.answer(deny, show_alert=True)
                else:
                    await event.answer(deny)
                return None
            return await handler(event, *args, **kwargs)

        return wrapped

    return deco
