"""Time helpers. Everything is stored as naive local ISO strings; anything a
person reads goes through fmt_time / fmt_day so the app never shows 24-hour time."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import os

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def weekday_key(d: date) -> str:
    return DAYS[d.weekday()]


def parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(value).replace(tzinfo=None)


def parse_hm(value: str) -> time:
    h, m = value.split(":")[:2]
    return time(int(h), int(m))


def iso(dt: datetime) -> str:
    return dt.replace(second=0, microsecond=0).isoformat(timespec="seconds")


def minutes_between(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def fmt_time(dt) -> str:
    """6:45 AM, 9:30 PM, 12:00 PM. Never 24-hour."""
    if isinstance(dt, str):
        dt = parse_dt(dt) if "T" in dt else datetime.combine(date.today(), parse_hm(dt))
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {suffix}"


def fmt_day(dt) -> str:
    """Thu 8:00 AM"""
    if isinstance(dt, str):
        dt = parse_dt(dt)
    return f"{dt.strftime('%a')} {fmt_time(dt)}"


def fmt_minutes(total: int) -> str:
    """90 -> '1 hr 30 min'"""
    total = int(round(total))
    h, m = divmod(total, 60)
    if h and m:
        return f"{h} hr {m} min"
    if h:
        return f"{h} hr"
    return f"{m} min"


DEMO_USER = "demo"


def local_now(tz_name: str = "America/New_York", user_id: str = None) -> datetime:
    """Current local time, minute precision.

    PACE_DEMO_NOW pins the clock for the shared demo plan only (so the video looks the same every
    take) while everyone else keeps the real date. PACE_NOW pins it for everyone (tests)."""
    pinned = os.environ.get("PACE_NOW")
    if not pinned and user_id == DEMO_USER:
        pinned = os.environ.get("PACE_DEMO_NOW")
    if pinned:
        return parse_dt(pinned)
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = ZoneInfo("America/New_York")
    return datetime.now(zone).replace(tzinfo=None, second=0, microsecond=0)


def ceil_to(dt: datetime, step_min: int = 5) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    over = dt.minute % step_min
    return dt if over == 0 else dt + timedelta(minutes=step_min - over)
