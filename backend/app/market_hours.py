"""Trading hours per exchange for the retrieval jobs: outside them the sources deliver no new candles, so the job saves
the requests (rate limits of the free tiers, compute time on the server). Each exchange has its own time zone.
Holidays are deliberately not modeled (no calendar in the project); a retrieval on a holiday only costs a few
requests and returns nothing wrong. Unknown exchanges always count as active."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

GRACE = timedelta(minutes=30)  # lag so the last candles arrive

# Exchange -> (time zone, start, end). US including pre-market from 04:00 and after-hours until 20:00,
# XETRA from the pre-trading phase 08:00 to the close 17:30 (with closing auction, plus buffer until 18:00).
SESSIONS: dict[str, tuple[ZoneInfo, time, time]] = {
    "XNYS": (ZoneInfo("America/New_York"), time(4, 0), time(20, 0)),
    "XNAS": (ZoneInfo("America/New_York"), time(4, 0), time(20, 0)),
    "XETR": (ZoneInfo("Europe/Berlin"), time(8, 0), time(18, 0)),
}


def session_active(exchange: str, now: datetime | None = None) -> bool:
    if exchange not in SESSIONS:
        return True
    tz, start_t, end_t = SESSIONS[exchange]
    local = (now or datetime.now(UTC)).astimezone(tz)
    if local.weekday() >= 5:
        return False
    start = local.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
    end = local.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0) + GRACE
    return start <= local <= end
