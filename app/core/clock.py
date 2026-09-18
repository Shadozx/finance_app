from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """The single source of "now" for stored timestamps: always timezone-aware UTC."""

    return datetime.now(UTC)


def today() -> date:
    """Calendar day in UTC, the same zone the stored instants use.

    The process timezone is deliberately not consulted: the answer must not
    depend on where the app runs.
    """

    return utc_now().date()
