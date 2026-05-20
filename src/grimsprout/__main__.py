"""Entry point: python -m grimsprout."""

from __future__ import annotations

import asyncio

from grimsprout.bot.app import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
