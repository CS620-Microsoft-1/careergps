"""Record latency, tokens and estimated cost for every Foundry Agent call in agent_calls.

Every `client.responses.create` in app/ goes through `call(...)` (tests/test_agent_calls.py checks this):

    response = agent_calls.call("resources-agent", None, client.responses.create, conversation=..., input=...)

Who made the call comes from context, not arguments:
- RequestContextMiddleware gives each request an empty holder; get_current_user fills in user_id.
  The holder is one shared dict, so a dependency running in a worker thread can still fill it.
- bind_run(run_id) marks calls made for one Skill Gap run.
- Work handed to another thread must carry the context along: use `in_context(fn)` as the thread target.

Recording never changes the call's outcome: a failed write is logged and dropped.
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from app.services.model_prices import estimate_cost

logger = logging.getLogger(__name__)

T = TypeVar("T")

_request: contextvars.ContextVar[dict | None] = contextvars.ContextVar("agent_call_request", default=None)
_run_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar("agent_call_run_id", default=None)

_RESPONSE_STATUSES = {"completed", "incomplete", "failed", "cancelled", "queued", "in_progress"}


# ---- context -------------------------------------------------------------------------------------

def start_request() -> contextvars.Token:
    """Give the current request a fresh holder for its user id. Called by RequestContextMiddleware."""
    return _request.set({})


def end_request(token: contextvars.Token) -> None:
    _request.reset(token)


def set_user(user_id: uuid.UUID | str | None) -> None:
    """Remember the signed-in user for this request's Agent calls. No-op outside a request."""
    holder = _request.get()
    if holder is not None and user_id is not None:
        holder["user_id"] = _uuid(user_id)


@contextmanager
def bind_run(run_id: uuid.UUID | str | None) -> Iterator[None]:
    """Mark Agent calls inside this block as part of one Skill Gap run."""
    token = _run_id.set(_uuid(run_id))
    try:
        yield
    finally:
        _run_id.reset(token)


def in_context(fn: Callable[..., T]) -> Callable[..., T]:
    """`fn` bound to a copy of the current context, for use as a thread or executor target.

    Threads do not inherit contextvars, so without this a call made in a worker thread has no user.
    Each call of in_context makes its own copy, so one result must not be run by two threads at once.
    """
    context = contextvars.copy_context()
    return lambda *args, **kwargs: context.run(fn, *args, **kwargs)


def _uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


# ---- sinks ---------------------------------------------------------------------------------------

class Sink(Protocol):
    def write(self, row: dict[str, Any]) -> None: ...


class DatabaseSink:
    """Insert each row in its own short transaction, apart from the request's session."""

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def write(self, row: dict[str, Any]) -> None:
        if self._session_factory is None:
            from app.db.session import SessionLocal  # Lazy: importing it needs DATABASE_URL.

            self._session_factory = SessionLocal
        from app.models.agent_call import AgentCall

        with self._session_factory() as session:
            session.add(AgentCall(**row))
            session.commit()


class MemorySink:
    """Keeps rows in a list; for tests."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def write(self, row: dict[str, Any]) -> None:
        self.rows.append(row)


_sink: Sink | None = None


def use_sink(sink: Sink) -> None:
    global _sink
    _sink = sink


def _current_sink() -> Sink:
    global _sink
    if _sink is None:
        _sink = DatabaseSink()
    return _sink


# ---- recording -----------------------------------------------------------------------------------

def call(agent: str, agent_version: str | None, create: Callable[..., T], /, **kwargs: Any) -> T:
    """Run `create(**kwargs)` (a responses.create) and record one agent_calls row for it.

    Returns the response or re-raises the error unchanged.
    """
    started = time.perf_counter()
    response = None
    error: BaseException | None = None
    try:
        response = create(**kwargs)
        return response
    except BaseException as caught:
        error = caught
        raise
    finally:
        latency_ms = round((time.perf_counter() - started) * 1000)
        try:
            _record(agent, agent_version, response, error, latency_ms)
        except Exception as record_error:
            logger.warning("Could not record Agent call for %s (%s)", agent, type(record_error).__name__)


def _record(agent: str, agent_version: str | None, response: Any, error: BaseException | None,
            latency_ms: int) -> None:
    usage = _usage(response)
    model = _field(response, "model")
    model = model if isinstance(model, str) else None
    cost = estimate_cost(model, usage["input_tokens"], usage["cached_tokens"], usage["output_tokens"])
    if model and cost is None and usage["input_tokens"] is not None:
        logger.warning("No price listed for model %s; agent_calls.cost_usd left empty", model)
    holder = _request.get() or {}
    row = {
        "agent": agent,
        "agent_version": agent_version,
        "model": model,
        "user_id": holder.get("user_id"),
        "run_id": _run_id.get(),
        "status": _status(response, error),
        "error_type": type(error).__name__ if error is not None else None,
        "latency_ms": max(latency_ms, 0),
        **usage,
        "cost_usd": cost.quantize(Decimal("0.00000001")) if cost is not None else None,
    }
    _current_sink().write(row)


def _status(response: Any, error: BaseException | None) -> str:
    if error is not None:
        return "timeout" if "Timeout" in type(error).__name__ else "error"
    status = _field(response, "status")
    # Some clients return no status for a finished response; a response with no error is completed.
    return status if status in _RESPONSE_STATUSES else "completed"


def _usage(response: Any) -> dict[str, int | None]:
    usage = _field(response, "usage")
    return {
        "input_tokens": _count(_field(usage, "input_tokens")),
        "cached_tokens": _count(_field(_field(usage, "input_tokens_details"), "cached_tokens")),
        "output_tokens": _count(_field(usage, "output_tokens")),
        "reasoning_tokens": _count(_field(_field(usage, "output_tokens_details"), "reasoning_tokens")),
    }


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
