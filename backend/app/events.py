"""Worker -> API: the worker writes events to the 'events' table, the API process reads them and
forwards them via WebSocket. Redis can replace this later (same publish()/poll() interface)."""
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from app.models import Event, utcnow


def publish(db: Session, type_: str, payload: dict[str, Any]) -> None:
    db.add(Event(type=type_, payload=payload))
    db.commit()


def poll(db: Session, after_id: int, limit: int = 200) -> list[Event]:
    return list(db.scalars(select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)))


EVENT_KEEP = timedelta(hours=24)


def prune(db: Session) -> int:
    """The table is only a queue for open WebSocket connections (they read from their connection onwards).
    Without cleanup it grows with every price update of every instrument."""
    res = db.execute(delete(Event).where(Event.created_at < utcnow() - EVENT_KEEP))
    db.commit()
    return cast("CursorResult[Any]", res).rowcount or 0
