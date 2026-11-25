"""Structured progress shared by the worker and the runtime."""
from datetime import datetime, timezone
from uuid import uuid4

PREFIX = "TRANSFER_ACTIVITY "


def activity(kind, title, detail=None, code=None):
    event = dict(id=uuid4().hex, at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"), kind=kind, title=title)
    if detail is not None:
        event["detail"] = detail
    if code is not None:
        event["code"] = code
    return event


def count(value):
    return f"{value:,}".replace(",", ".")
