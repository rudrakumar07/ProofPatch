"""Tiny in-process event publisher shared by the CLI and the API.

Events are persisted by the sink *before* being broadcast to listeners, which
guarantees the dashboard can reconnect and reconstruct full history.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .domain import RunEventModel

EventListener = Callable[[RunEventModel], None]


class EventSink(Protocol):
    def emit(
        self,
        event_type: str,
        message: str,
        *,
        step: str | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEventModel: ...


class EventPublisher:
    """Sequences events, hands them to a persistence hook, then notifies listeners."""

    def __init__(
        self,
        run_id: str,
        persist: Callable[[RunEventModel], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self._persist = persist
        self._listeners: list[EventListener] = []
        self._history: list[RunEventModel] = []
        self._sequence = 0

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def history(self) -> list[RunEventModel]:
        return list(self._history)

    def emit(
        self,
        event_type: str,
        message: str,
        *,
        step: str | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEventModel:
        self._sequence += 1
        event = RunEventModel(
            run_id=self.run_id,
            sequence=self._sequence,
            type=event_type,
            step=step,
            status=status,
            message=message,
            payload=payload or {},
        )

        # Persist first so history survives a broadcaster crash.
        if self._persist is not None:
            self._persist(event)

        self._history.append(event)
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                # A faulty subscriber must never break the verification run.
                continue
        return event


__all__ = ["EventListener", "EventPublisher", "EventSink"]
