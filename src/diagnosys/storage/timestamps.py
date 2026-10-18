"""Helpers for storing timestamps consistently in SQLite."""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC timestamp, treating naive values as UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_timestamp(value: datetime) -> str:
    """Serialize UTC timestamps without relying on sqlite3's deprecated adapters."""
    return as_utc(value).isoformat(sep=" ", timespec="microseconds")


def parse_timestamp(value: datetime | str) -> datetime:
    """Parse a stored timestamp and return it as an aware UTC datetime."""
    if isinstance(value, datetime):
        return as_utc(value)

    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return as_utc(datetime.fromisoformat(text))
