from datetime import UTC, datetime


def utc_now() -> datetime:
    """The single source of "now" for stored timestamps: always timezone-aware UTC."""

    return datetime.now(UTC)
