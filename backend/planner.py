"""The scheduling algorithm.

plan() is a pure function: same inputs, same output. Sleep is fixed; study only
goes into free time between waking up and the study cutoff. Work that doesn't fit
is reported as at-risk and shown as overflow that eats into that night's sleep,
so the cost is visible instead of hidden.
"""
from datetime import date, datetime, timedelta

from .timeutil import (ceil_to, fmt_time, iso, minutes_between, parse_dt, parse_hm,
                       weekday_key)

CHUNK_MIN = 45          # target chunk length
MIN_CHUNK_MIN = 15      # never schedule a block shorter than this
BUFFER_MIN = 10         # gap between blocks
WIND_DOWN_MIN = 30      # no work in the 30 min before bedtime
AFTER_SHIFT_MIN = 30    # rest after a shift before any study
RECOVERY_WINDOW_H = 48  # recovery mode: tonight only holds work due this soon

WORK_HOURS_WARN = 15
WORK_HOURS_RED = 20


# ---------- settings-derived times ----------

def wake_on(settings, d: date) -> datetime:
    return datetime.combine(d, parse_hm(settings["wake_times"][weekday_key(d)]))


def bedtime_for(settings, d: date) -> datetime:
    """Bedtime for the night of d = next morning's wake time minus the sleep goal."""
    return wake_on(settings, d + timedelta(days=1)) - timedelta(minutes=settings["sleep_goal_min"])


def cutoff_for(settings, d: date) -> datetime:
    return bedtime_for(settings, d) - timedelta(minutes=WIND_DOWN_MIN)


def school_on(settings, d: date):
    block = (settings.get("school_blocks") or {}).get(weekday_key(d))
    if not block:
        return None
    return datetime.combine(d, parse_hm(block[0])), datetime.combine(d, parse_hm(block[1]))


def is_school_day(settings, d: date) -> bool:
    return school_on(settings, d) is not None


def daily_cap(settings, d: date) -> int:
    if is_school_day(settings, d + timedelta(days=1)):
        return settings["max_study_school_night_min"]
    return settings["max_study_weekend_day_min"]


def effective_deadline(settings, due: datetime) -> datetime:
    """Due during school (or the commute in) means it must be done the night before."""
    school = school_on(settings, due.date())
    if school:
        commute = timedelta(minutes=settings.get("commute_min", 0))
        if school[0] - commute <= due <= school[1]:
            return cutoff_for(settings, due.date() - timedelta(days=1))
    return due


# ---------- helpers ----------

def split(total: int, chunk: int = CHUNK_MIN, min_chunk: int = MIN_CHUNK_MIN) -> list:
    """split(300, 45, 15) -> [45,45,45,45,45,45,30]. A tail under min_chunk merges into the previous piece."""
    if total <= 0:
        return []
    pieces = [chunk] * (total // chunk)
    rest = total % chunk
    if rest:
        if rest < min_chunk and pieces:
            pieces[-1] += rest
        else:
            pieces.append(rest)
    return pieces


def expand_events(events, first: date, last: date) -> list:
    """Concrete occurrences overlapping [first, last]. Recurring events repeat on their weekdays
    starting from their own start date."""
    out = []
    for e in events:
        start, end = parse_dt(e["start"]), parse_dt(e["end"])
        if end <= start:
            end += timedelta(days=1)
        rec = e.get("recurring")
        if rec and rec.get("days"):
            length = end - start
            d = max(first, start.date())
            while d <= last:
                if weekday_key(d) in rec["days"]:
                    s = datetime.combine(d, start.time())
                    out.append({**e, "start": s, "end": s + length})
                d += timedelta(days=1)
        elif end.date() >= first and start.date() <= last:
            out.append({**e, "start": start, "end": end})
    out.sort(key=lambda o: o["start"])
    return out


def subtract(window, busy) -> list:
    """window minus every busy interval, keeping pieces of at least MIN_CHUNK_MIN."""
    slots = [window]
    for bs, be in sorted(busy):
        nxt = []
        for s, e in slots:
            if be <= s or bs >= e:
                nxt.append((s, e))
                continue
            if bs > s:
                nxt.append((s, bs))
            if be < e:
                nxt.append((be, e))
        slots = nxt
    return [(s, e) for s, e in slots if minutes_between(s, e) >= MIN_CHUNK_MIN]


def week_bounds(d: date):
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def work_hours(events, today: date) -> float:
    monday, sunday = week_bounds(today)
    total = sum(minutes_between(o["start"], o["end"])
                for o in expand_events(events, monday, sunday)
                if o["kind"] == "shift" and monday <= o["start"].date() <= sunday)
    return round(total / 60, 1)


def describe_day(settings, occurrences, blocked, d: date) -> dict:
    """The fixed shape of a day: wake, school, events, time off. Shared by planned and past days."""
    school = school_on(settings, d)
    return {
        "date": d.isoformat(),
        "wake": iso(wake_on(settings, d)),
        "cutoff": iso(cutoff_for(settings, d)),
        "bedtime": iso(bedtime_for(settings, d)),
        "school": [iso(school[0]), iso(school[1])] if school else None,
        "events": [{"id": o.get("id"), "kind": o["kind"], "title": o["title"],
                    "start": iso(o["start"]), "end": iso(o["end"]), "source": o.get("source")}
                   for o in occurrences if o["start"].date() == d],
        "blocked": [{"id": b.get("id"), "start": b["start"], "end": b["end"]} for b in blocked
                    if parse_dt(b["start"]).date() <= d <= parse_dt(b["end"]).date()],
    }


def past_days(settings, events, blocked, dates, reported_sleep: dict):
    """Days of this week that already happened. Nothing is planned for them; each night shows the
    sleep the person reported in the next morning's check-in (reported_sleep: date -> minutes)."""
    if not dates:
        return [], []
    occurrences = expand_events(events, dates[0], dates[-1] + timedelta(days=1))
    goal = settings["sleep_goal_min"]
    days, nights = [], []
    for d in dates:
        days.append({**describe_day(settings, occurrences, blocked, d), "cap_min": 0, "used_min": 0, "past": True})
        slept = reported_sleep.get((d + timedelta(days=1)).isoformat())
        status = (None if slept is None else
                  "green" if slept >= goal else "yellow" if slept >= goal - 60 else "red")
        nights.append({"date": d.isoformat(), "bedtime": iso(bedtime_for(settings, d)), "sleep_start": None,
                       "wake": iso(wake_on(settings, d + timedelta(days=1))), "sleep_min": slept,
                       "status": status or "unknown", "overflow_min": 0, "reported": True})
    return days, nights


# ---------- the planner ----------

def plan(settings, events, tasks, blocked, now: datetime, days: int = 7,
         relaxed: bool = False, recovery: bool = False) -> dict:
    now = parse_dt(now)
    today = now.date()
    day_list = [today + timedelta(days=i) for i in range(days)]
    horizon_end = cutoff_for(settings, day_list[-1])
    occurrences = expand_events(events, today - timedelta(days=1), day_list[-1] + timedelta(days=1))
    blocked_iv = [(parse_dt(b["start"]), parse_dt(b["end"])) for b in blocked]
    commute = timedelta(minutes=settings.get("commute_min", 0))

    slots, caps, used = {}, {}, {}
    for d in day_list:
        start = wake_on(settings, d)
        if d == today:
            start = max(start, ceil_to(now))
        cutoff = cutoff_for(settings, d)
        busy = []
        school = school_on(settings, d)
        if school:
            # Getting ready, commuting, school, commuting home. No study squeezed in before school.
            busy.append((wake_on(settings, d), school[1] + commute))
        for o in occurrences:
            rest = AFTER_SHIFT_MIN if o["kind"] == "shift" else 0
            busy.append((o["start"], o["end"] + timedelta(minutes=rest)))
        busy.extend(blocked_iv)
        slots[d] = subtract((start, cutoff), busy) if start < cutoff else []
        caps[d] = int(daily_cap(settings, d) * (1.5 if relaxed else 1))
        used[d] = 0

    blocks, at_risk, risk_tasks, deferred = [], [], [], []

    todo = [dict(t) for t in tasks if not t.get("completed")]  # copies: plan() stays pure
    for t in todo:
        t["_due"] = parse_dt(t["due"])
        t["_deadline"] = effective_deadline(settings, t["_due"])
        t["_remaining"] = max(0, t["planned_min"] - t.get("done_min", 0))
    todo.sort(key=lambda t: (t["_deadline"], -t["_remaining"], t.get("id", 0)))

    def place(task, amount):
        """Put up to `amount` minutes of task in the earliest usable slot. Returns minutes placed."""
        deadline = task["_deadline"]
        for d in day_list:
            if wake_on(settings, d) >= deadline:
                break
            if recovery and d == today and task["_due"] > now + timedelta(hours=RECOVERY_WINDOW_H):
                continue
            cap_left = caps[d] - used[d]
            need = min(MIN_CHUNK_MIN, amount)
            if cap_left < need:
                continue
            # First pass: a slot that holds the whole piece. Second pass: the earliest partial fit.
            for whole in (True, False):
                for i, (s, e) in enumerate(slots[d]):
                    avail = minutes_between(s, min(e, deadline))
                    fit = min(avail, cap_left, amount)
                    if whole and fit < amount:
                        continue
                    if fit < need:
                        continue
                    if 0 < amount - fit < MIN_CHUNK_MIN:  # don't leave a sliver behind
                        fit = amount - MIN_CHUNK_MIN
                        if fit < MIN_CHUNK_MIN:
                            continue
                    end = s + timedelta(minutes=fit)
                    blocks.append({
                        "task_id": task.get("id"), "title": task["title"],
                        "subject": task.get("subject"), "start": end - timedelta(minutes=fit),
                        "end": end, "minutes": fit,
                    })
                    used[d] += fit
                    slots[d][i] = (end + timedelta(minutes=BUFFER_MIN), e)
                    return fit
        return 0

    for t in todo:
        short = 0
        for chunk in split(t["_remaining"]):
            left = chunk
            while left > 0:
                got = place(t, left)
                if not got:
                    break
                left -= got
            short += left
        if recovery and t["_due"] > now + timedelta(hours=RECOVERY_WINDOW_H):
            deferred.append(t.get("id"))
        if short > 0 and t["_deadline"] <= horizon_end:
            at_risk.append({
                "task_id": t.get("id"), "title": t["title"], "due": iso(t["_due"]),
                "short_by_min": short, "overdue": t["_deadline"] <= now,
            })
            risk_tasks.append(t)

    # Overflow: put missing minutes after the cutoff on the night before the deadline.
    overflow = {d: 0 for d in day_list}
    for r, task in zip(at_risk, risk_tasks):
        if r["overdue"]:
            continue
        nights = [d for d in day_list if cutoff_for(settings, d) <= task["_deadline"]]
        if nights:
            overflow[nights[-1]] += r["short_by_min"]
            r["overflow_night"] = nights[-1].isoformat()

    goal = settings["sleep_goal_min"]
    nights_out = []
    for d in day_list:
        bed = bedtime_for(settings, d)
        next_wake = wake_on(settings, d + timedelta(days=1))
        sleep_start, reasons = bed, []
        for o in occurrences:
            # Wind-down rest only follows work. A short prayer or practice ending before bedtime
            # costs no sleep; only one that runs past bedtime pushes sleep later.
            rest = timedelta(minutes=AFTER_SHIFT_MIN if o["kind"] == "shift" else 0)
            if o["start"] < next_wake and o["end"] + rest > bed and o["start"] >= wake_on(settings, d):
                rest_end = o["end"] + rest
                if rest_end > sleep_start:
                    sleep_start = rest_end
                    reasons = [r for r in reasons if "ends" not in r]
                    reasons.append(f"{o['title']} ends {fmt_time(o['end'])}")
        if overflow[d]:
            sleep_start += timedelta(minutes=overflow[d])
            reasons.append(f"{overflow[d]} min of work that didn't fit")
        sleep_min = max(0, minutes_between(sleep_start, next_wake))
        status = "green" if sleep_min >= goal else "yellow" if sleep_min >= goal - 60 else "red"
        night = {"date": d.isoformat(), "bedtime": iso(bed), "sleep_start": iso(sleep_start),
                 "wake": iso(next_wake), "sleep_min": sleep_min, "status": status,
                 "overflow_min": overflow[d]}
        if reasons:
            night["reason"] = " + ".join(reasons)
        nights_out.append(night)

    hours = work_hours(events, today)
    warnings = []
    if hours > WORK_HOURS_WARN:
        warnings.append(f"Over {WORK_HOURS_WARN} work hours this week")
    work_status = "red" if hours > WORK_HOURS_RED else "yellow" if hours > WORK_HOURS_WARN else "green"

    # Slack: free minutes still usable under the caps.
    slack_min = 0
    for d in day_list:
        free = sum(max(0, minutes_between(s, e)) for s, e in slots[d])
        slack_min += max(0, min(free, caps[d] - used[d]))

    blocks.sort(key=lambda b: b["start"])
    day_info = [{**describe_day(settings, occurrences, blocked, d), "cap_min": caps[d], "used_min": used[d]}
                for d in day_list]

    return {
        "generated_at": iso(now),
        "relaxed": relaxed,
        "recovery": recovery,
        "blocks": [{**b, "start": iso(b["start"]), "end": iso(b["end"])} for b in blocks],
        "nights": nights_out,
        "days": day_info,
        "at_risk": at_risk,
        "deferred_task_ids": deferred,
        "work_hours_this_week": hours,
        "work_hours_status": work_status,
        "warnings": warnings,
        "slack_min": slack_min,
        "week_has_slack": not at_risk and slack_min >= 90,
        "stop_time": iso(cutoff_for(settings, today)),
    }
