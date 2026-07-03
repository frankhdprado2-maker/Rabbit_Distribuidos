from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.shared.constants import EVENT_VERSION


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventEnvelope(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: int = EVENT_VERSION
    correlation_id: str
    causation_id: str | None = None
    id_orden: str
    timestamp: str = Field(default_factory=utc_now_iso)
    source: str
    attempt: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def build_event(
    *,
    event_type: str,
    source: str,
    id_orden: str,
    correlation_id: str,
    payload: dict[str, Any],
    causation_id: str | None = None,
    attempt: int = 0,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        source=source,
        id_orden=id_orden,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
        attempt=attempt,
    )


def build_next_event(
    previous: EventEnvelope,
    *,
    event_type: str,
    source: str,
    payload: dict[str, Any],
) -> EventEnvelope:
    return build_event(
        event_type=event_type,
        source=source,
        id_orden=previous.id_orden,
        correlation_id=previous.correlation_id,
        causation_id=previous.message_id,
        payload=payload,
        attempt=previous.attempt,
    )
