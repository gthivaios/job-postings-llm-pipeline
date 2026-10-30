"""Optional Opik tracing.

Call `configure("opik")` once at start-up to send traces to Opik. Otherwise `track` and
`update_span` are no-ops, so the pipeline runs the same without an Opik account.
"""

import functools
from collections.abc import Callable
from typing import Any

_enabled = False


def configure(mode: str) -> None:
    global _enabled
    _enabled = mode == "opik"
    if _enabled:
        # Opik reads OPIK_* from the process environment, so export them from .env
        from dotenv import load_dotenv

        load_dotenv(override=False)


def enabled() -> bool:
    return _enabled


def track(name: str, type: str = "general") -> Callable:
    """Decorator: an Opik span/trace when tracing is on, a plain call otherwise."""

    def decorator(fn: Callable) -> Callable:
        traced: Callable | None = None

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal traced
            if not _enabled:
                return fn(*args, **kwargs)
            if traced is None:
                import opik

                traced = opik.track(name=name, type=type, ignore_arguments=["self"])(fn)
            return traced(*args, **kwargs)

        return wrapper

    return decorator


def update_span(**kwargs: Any) -> None:
    if _enabled:
        from opik import opik_context

        opik_context.update_current_span(**kwargs)


def update_trace(**kwargs: Any) -> None:
    if _enabled:
        from opik import opik_context

        opik_context.update_current_trace(**kwargs)


def flush() -> None:
    if _enabled:
        import opik

        opik.flush_tracker()
