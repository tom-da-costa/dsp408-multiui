"""asyncio helpers."""

from __future__ import annotations

import asyncio


async def cancel_and_wait(task: asyncio.Task[object]) -> None:
    """Cancel ``task`` and wait for it to end.

    ``with suppress(CancelledError): await task`` would also swallow the cancellation of the
    task running this code (when it is itself cancelled while waiting), which then carries on
    as if nothing happened: a stop that never ends. Only the awaited task's cancellation is
    absorbed here.
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
