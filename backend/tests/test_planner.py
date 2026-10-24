from datetime import datetime, timedelta

from backend import planner
from backend.planner import plan, split
from backend.timeutil import parse_dt

from .conftest import NOW, shift, task


def night(result, d):
    return next(n for n in result["nights"] if n["date"] == d)


def test_split():
    assert split(300, 45, 15) == [45, 45, 45, 45, 45, 45, 30]
    assert split(100, 45, 15) == [45, 55]   # tail of 10 merges into the previous piece
    assert split(10) == [10]
    assert split(0) == []


def test_task_due_tomorrow_fits_tonight(settings):
    r = plan(settings, [], [task(1, "Chem", "2026-10-20T23:00:00", 60)], [], NOW)
    tonight = [b for b in r["blocks"] if b["start"].startswith("2026-10-19")]
    assert sum(b["minutes"] for b in tonight) == 60
    cutoff = planner.cutoff_for(settings, NOW.date())
    assert all(parse_dt(b["end"]) <= cutoff for b in tonight)
    assert not r["at_risk"]


def test_nothing_after_cutoff_or_before_wake(settings):
    tasks = [task(i, f"T{i}", "2026-10-25T20:00:00", 200) for i in range(6)]
    r = plan(settings, [], tasks, [], NOW)
    for b in r["blocks"]:
        d = parse_dt(b["start"]).date()
        assert parse_dt(b["end"]) <= planner.cutoff_for(settings, d)
        assert parse_dt(b["start"]) >= planner.wake_on(settings, d)
    # overflow is reported, never planned
    assert all(n["overflow_min"] == 0 or n["status"] != "green" for n in r["nights"])


def test_no_overlap_with_school_shift_or_rest(settings):
    events = [shift(1, "2026-10-20T17:00:00", "2026-10-20T21:00:00")]
    tasks = [task(i, f"T{i}", "2026-10-25T20:00:00", 300) for i in range(4)]
    r = plan(settings, events, tasks, [], NOW)
    busy = []
    for i in range(7):
        d = NOW.date() + timedelta(days=i)
        sb = planner.school_on(settings, d)
        if sb:
            busy.append((sb[0] - timedelta(minutes=20), sb[1] + timedelta(minutes=20)))
    busy.append((datetime(2026, 10, 20, 17, 0), datetime(2026, 10, 20, 21, 30)))  # shift + 30 min rest
    for b in r["blocks"]:
        s, e = parse_dt(b["start"]), parse_dt(b["end"])
        for bs, be in busy:
            assert e <= bs or s >= be, f"{b} overlaps {bs}-{be}"


def test_blocks_never_overlap_each_other(settings):
    tasks = [task(i, f"T{i}", "2026-10-24T20:00:00", 150) for i in range(5)]
    r = plan(settings, [], tasks, [], NOW)
    spans = sorted((parse_dt(b["start"]), parse_dt(b["end"])) for b in r["blocks"])
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 + timedelta(minutes=planner.BUFFER_MIN) <= s2
    assert all(b["minutes"] >= planner.MIN_CHUNK_MIN for b in r["blocks"])


def test_daily_caps_and_relaxed(settings):
    tasks = [task(1, "Big", "2026-10-26T20:00:00", 2000)]
    normal = plan(settings, [], tasks, [], NOW)
    relaxed = plan(settings, [], tasks, [], NOW, relaxed=True)
    for d_normal, d_relaxed in zip(normal["days"], relaxed["days"]):
        assert d_normal["used_min"] <= d_normal["cap_min"]
        assert d_relaxed["cap_min"] == int(d_normal["cap_min"] * 1.5)
        assert d_relaxed["used_min"] <= d_relaxed["cap_min"]
    assert normal["days"][0]["cap_min"] == 120      # Monday: school tomorrow
    assert normal["days"][4]["cap_min"] == 240      # Friday: no school Saturday


def test_too_big_is_at_risk_and_night_turns_red(settings):
    # Due Tue 8:00 AM (during school) so only Monday evening counts: 120 min cap.
    r = plan(settings, [], [task(7, "Essay", "2026-10-20T08:00:00", 600)], [], NOW)
    assert r["at_risk"] == [{"task_id": 7, "title": "Essay", "due": "2026-10-20T08:00:00",
                             "short_by_min": 480, "overdue": False, "overflow_night": "2026-10-19"}]
    assert night(r, "2026-10-19")["status"] == "red"
    assert night(r, "2026-10-19")["sleep_min"] == 510 - 480


def test_late_shift_turns_night_red(settings):
    r = plan(settings, [shift(1, "2026-10-20T20:00:00", "2026-10-20T23:00:00")], [], [], NOW)
    tue = night(r, "2026-10-20")
    assert tue["status"] == "red"
    assert tue["sleep_min"] == 435          # asleep 11:30 PM, up 6:45 AM
    assert "11:00 PM" in tue["reason"]      # 12-hour time in anything a person reads


def activity(id, start, end, recurring=None, title="Prayer"):
    return {"id": id, "kind": "activity", "title": title, "start": start, "end": end, "recurring": recurring}


def test_short_prayer_before_bed_costs_no_sleep(settings):
    # Bedtime Mon night is 10:15 PM. A 9:50-10:00 PM prayer ends before it: full sleep.
    r = plan(settings, [activity(1, "2026-10-19T21:50:00", "2026-10-19T22:00:00")], [], [], NOW)
    assert night(r, "2026-10-19")["sleep_min"] == 510
    # One that runs past bedtime pushes sleep back by exactly the overrun (no 30-min rest).
    r = plan(settings, [activity(1, "2026-10-19T22:10:00", "2026-10-19T22:25:00")], [], [], NOW)
    assert night(r, "2026-10-19")["sleep_min"] == 500


def test_daily_prayer_times_are_planned_around(settings):
    every_day = {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
    events = [activity(1, "2026-10-19T17:05:00", "2026-10-19T17:20:00", every_day),
              activity(2, "2026-10-19T18:30:00", "2026-10-19T18:45:00", every_day)]
    r = plan(settings, events, [task(1, "Essay", "2026-10-25T20:00:00", 600)], [], NOW)
    for b in r["blocks"]:
        s, e = parse_dt(b["start"]), parse_dt(b["end"])
        for hh, mm, length in [(17, 5, 15), (18, 30, 15)]:
            ps = s.replace(hour=hh, minute=mm)
            assert e <= ps or s >= ps + timedelta(minutes=length), b
    assert r["work_hours_this_week"] == 0     # prayer isn't work


def test_shift_overflow_red_then_rebalance_green(settings):
    tasks = [task(1, "History essay", "2026-10-22T08:00:00", 330, subject="history")]
    baseline = plan(settings, [], tasks, [], NOW)
    assert all(n["status"] == "green" for n in baseline["nights"])

    # A long Wednesday shift wipes out Wednesday's study time.
    events = [shift(1, "2026-10-21T15:00:00", "2026-10-21T21:30:00")]
    added = plan(settings, events, tasks, [], NOW)
    assert night(added, "2026-10-21")["status"] == "red"
    assert added["at_risk"][0]["short_by_min"] == 90

    rebalanced = plan(settings, events, tasks, [], NOW, relaxed=True)
    assert not rebalanced["at_risk"]
    assert all(n["status"] == "green" for n in rebalanced["nights"])


def test_due_during_school_counts_as_night_before(settings):
    r = plan(settings, [], [task(1, "Lab", "2026-10-21T10:00:00", 200)], [], NOW)
    assert all(not b["start"].startswith("2026-10-21") for b in r["blocks"])
    cutoff_tue = planner.cutoff_for(settings, datetime(2026, 10, 20).date())
    assert all(parse_dt(b["end"]) <= cutoff_tue for b in r["blocks"])


def test_recurring_shifts_and_work_hours(settings):
    events = [shift(1, "2026-10-13T17:00:00", "2026-10-13T21:00:00", {"days": ["tue", "thu"]}),
              shift(2, "2026-10-17T10:00:00", "2026-10-17T16:00:00", {"days": ["sat"]})]
    r = plan(settings, events, [], [], NOW)
    assert r["work_hours_this_week"] == 14.0
    assert r["warnings"] == []
    events.append(shift(3, "2026-10-23T17:00:00", "2026-10-23T22:00:00"))
    r = plan(settings, events, [], [], NOW)
    assert r["work_hours_this_week"] == 19.0
    assert r["warnings"] == ["Over 15 work hours this week"]
    assert r["work_hours_status"] == "yellow"


def test_recovery_keeps_tonight_for_urgent_work(settings):
    tasks = [task(1, "Due soon", "2026-10-20T20:00:00", 45),
             task(2, "Due later", "2026-10-24T20:00:00", 90)]
    r = plan(settings, [], tasks, [], NOW, recovery=True)
    tonight = {b["task_id"] for b in r["blocks"] if b["start"].startswith("2026-10-19")}
    assert tonight == {1}
    assert 2 in r["deferred_task_ids"]


def test_plan_is_pure(settings):
    tasks = [task(1, "Chem", "2026-10-20T23:00:00", 60)]
    snapshot = [dict(t) for t in tasks]
    a = plan(settings, [], tasks, [], NOW)
    b = plan(settings, [], tasks, [], NOW)
    assert a == b
    assert tasks == snapshot
