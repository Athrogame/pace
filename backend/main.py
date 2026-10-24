"""Pace's API, public pages, and static frontend."""
import json
import os
import html
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from . import age_gate, auth, coach, db, decision_coach, estimates, parent_mail, planner, rate_limit, task_suggestions  # noqa: E402
from .models import (AuthIn, CalendarImportIn, CameUpIn, CheckinIn, DecisionCoachIn, EventIn, EventPatch, GoogleIn, GoogleTasksImportIn, GoogleTaskSuggestIn,  # noqa: E402
                     MinutesIn,
                     SettingsIn, TaskIn, TaskPatch, TextIn)
from .modes import pick_mode  # noqa: E402
from .safety import SAFETY_SCREEN, is_flagged  # noqa: E402
from .timeutil import fmt_minutes, iso, local_now, parse_dt  # noqa: E402

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
LEGAL_TEMPLATES = Path(__file__).resolve().parent / "legal_templates"
DEMO_USER = "demo"   # the shared plan behind ?as=demo; it must never become someone's account


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    if os.environ.get("PACE_REQUIRE_LEGAL_CONTACT") == "1":
        contact = (os.environ.get("PACE_CONTACT_EMAIL") or "").strip()
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", contact):
            raise RuntimeError("PACE_CONTACT_EMAIL is required for public Terms and Privacy Policy")
    if age_gate.required():
        age_gate.secret()
        parent_mail.config()
    yield


app = FastAPI(title="Pace", lifespan=lifespan)


# Only our own files, Google Fonts, and Google's sign-in button may load. Nothing may frame Pace.
GSI = "https://accounts.google.com/gsi/"
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    f"script-src 'self' {GSI}client",
    f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {GSI}style",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https://*.googleusercontent.com",
    f"connect-src 'self' {GSI} https://www.googleapis.com/calendar/ https://tasks.googleapis.com",   # read-only Google imports
    f"frame-src {GSI}",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Google sign-in needs the page's origin in the referrer; nothing more leaves the site.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    # Lets Google's sign-in popup report back without other windows getting a handle on Pace.
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
}


@app.middleware("http")
async def security_and_caching(request, call_next):
    retry = rate_limit.check(request)
    if retry is not None:
        return JSONResponse({"detail": "Too many requests. Try again later."}, status_code=429,
                            headers={"Retry-After": str(retry), "Cache-Control": "no-store", **SECURITY_HEADERS})
    denied = None
    if request.cookies.get(auth.SESSION_COOKIE) and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        scheme = "https" if os.environ.get("RENDER") == "true" else request.url.scheme
        expected_origin = f"{scheme}://{request.headers.get('host', '')}"
        if request.headers.get("origin") != expected_origin:
            denied = JSONResponse({"detail": "Invalid request origin."}, status_code=403)
    if denied is None and age_gate.required():
        # This gate runs before route dependencies, including the account and plan APIs.
        # A signed cookie alone is insufficient for a child: approval can be revoked.
        age = age_gate.read(request.cookies.get(age_gate.COOKIE))
        request.state.age = age
        path = request.url.path
        protected = path.startswith(("/settings", "/events", "/calendar", "/tasks",
                                     "/plan", "/checkins", "/mode", "/coach", "/decision",
                                     "/came-up", "/estimates", "/auth/", "/me", "/safety/check"))
        if path == "/auth/config":
            protected = False
        if protected:
            if not age or age[0] == "child_pending":
                denied = JSONResponse({"detail": "Complete the age screen first."}, status_code=403)
            elif age[0] == "child":
                with db.connect() as age_conn:
                    if not age_gate.approved(age_conn, age[1]):
                        denied = JSONResponse({"detail": "Parent approval is no longer active."}, status_code=403)
                if denied is None and path.startswith(("/auth/", "/calendar", "/tasks/google")):
                    denied = JSONResponse({"detail": "This feature is unavailable for child plans."}, status_code=403)
    response = denied or await call_next(request)
    if response.status_code == 401 and request.cookies.get(auth.SESSION_COOKIE):
        _clear_session_cookie(response)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    # Behind Render's HTTPS proxy, tell browsers to always use HTTPS from now on.
    if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html", ".svg", ".json")):
        # Re-check frontend files each load (cheap 304s) so updates show up right away.
        response.headers["Cache-Control"] = "no-cache"
    elif not path.startswith(("/icons/",)):
        # API answers hold personal plans: never keep them in shared or disk caches.
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _bearer(authorization):
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _session_cookie(response, request, token):
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or \
        os.environ.get("RENDER") == "true" or os.environ.get("PACE_REQUIRE_DURABLE_DB") == "1"
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
                        httponly=True, secure=secure, samesite="strict", path="/")
    return response


def _clear_session_cookie(response):
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


def user_id(request: Request, x_user_id: str = Header(None)) -> str:
    """Signed in: the HttpOnly session cookie decides who you are. Otherwise use the random id,
    unless that id belongs to an account, which then needs a real sign-in."""
    token = request.cookies.get(auth.SESSION_COOKIE)
    conn = db.connect()
    try:
        if token:
            uid = auth.user_for_token(conn, token)
            if uid is None:
                raise HTTPException(401, "Your session ended. Please sign in again.")
            if age_gate.required() and request.state.age[0] == "child" and uid != request.state.age[1]:
                raise HTTPException(403, "This parent approval belongs to another plan.")
            return uid
        uid = (x_user_id or "").strip()
        if not uid or len(uid) > 64:
            raise HTTPException(400, "bad X-User-Id")
        if age_gate.required() and request.state.age[0] == "child" and uid != request.state.age[1]:
            raise HTTPException(403, "This parent approval belongs to another plan.")
        if auth.account_for_user(conn, uid):
            raise HTTPException(401, "Please sign in.")
        return uid
    finally:
        conn.close()


def conn_dep():
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def need_settings(conn, uid):
    s = db.load_settings(conn, uid)
    if s is None:
        raise HTTPException(404, "setup needed")
    return s


# ---------- shared planning context ----------

def now_for(settings) -> "datetime":
    """The current time for this plan (the demo plan can have its own pinned clock)."""
    return local_now(settings["timezone"], settings.get("user_id"))


def flag_recent(conn, uid, now) -> bool:
    row = conn.execute("SELECT 1 FROM safety_flags WHERE user_id = ? AND flagged_at >= ?",
                       (uid, iso(now - timedelta(hours=24)))).fetchone()
    return row is not None


def red_uses_7d(conn, uid, now) -> int:
    return conn.execute("SELECT COUNT(*) FROM blocked_times WHERE user_id = ? AND created_at >= ?",
                        (uid, iso(now - timedelta(days=7)))).fetchone()[0]


def record_flag(conn, uid, now):
    conn.execute("INSERT INTO safety_flags (user_id, flagged_at) VALUES (?, ?)", (uid, iso(now)))


def is_relaxed(settings, now) -> bool:
    return bool(settings.get("relaxed_until")) and settings["relaxed_until"] >= now.date().isoformat()


def context(conn, uid, days=7, extra_events=None):
    """Load everything, pick the mode, run the planner (recovery-aware)."""
    s = need_settings(conn, uid)
    now = now_for(s)
    events = db.load_events(conn, uid) + (extra_events or [])
    tasks = db.load_tasks(conn, uid)
    blocked = db.load_blocked(conn, uid)
    relaxed = is_relaxed(s, now)
    base = planner.plan(s, events, tasks, blocked, now, days=days, relaxed=relaxed)

    since = (now.date() - timedelta(days=6)).isoformat()
    checkins = [c for c in db.load_checkins(conn, uid, since)
                if any(c.get(k) is not None for k in ("sleep_min", "energy", "stress"))]
    mode, reasons = pick_mode(checkins, s["sleep_goal_min"], red_uses_7d(conn, uid, now),
                              flag_recent(conn, uid, now), base["week_has_slack"])
    result = base
    if mode == "recovery":
        result = planner.plan(s, events, tasks, blocked, now, days=days, relaxed=relaxed, recovery=True)
    result["mode"] = mode
    result["mode_reasons"] = reasons
    return {"settings": s, "now": now, "events": events, "tasks": tasks, "blocked": blocked,
            "plan": result, "mode": mode, "reasons": reasons, "relaxed": relaxed}


# ---------- settings ----------

@app.get("/settings")
def get_settings(uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    s["now"] = iso(now_for(s))
    return s


@app.put("/settings")
def put_settings(body: SettingsIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    now = local_now(body.timezone, uid)
    existing = conn.execute("SELECT created_at FROM settings WHERE user_id = ?", (uid,)).fetchone()
    conn.execute(
        """INSERT INTO settings (user_id, nickname, timezone, sleep_goal_min, wake_times, school_blocks,
               commute_min, max_study_school_night_min, max_study_weekend_day_min, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname, timezone=excluded.timezone,
               sleep_goal_min=excluded.sleep_goal_min, wake_times=excluded.wake_times,
               school_blocks=excluded.school_blocks, commute_min=excluded.commute_min,
               max_study_school_night_min=excluded.max_study_school_night_min,
               max_study_weekend_day_min=excluded.max_study_weekend_day_min""",
        (uid, body.nickname, body.timezone, body.sleep_goal_min, json.dumps(body.wake_times),
         json.dumps(body.school_blocks), body.commute_min, body.max_study_school_night_min,
         body.max_study_weekend_day_min, existing["created_at"] if existing else iso(now)),
    )
    return db.load_settings(conn, uid)


# ---------- events ----------

def _event_row(conn, uid, eid):
    row = conn.execute("SELECT * FROM events WHERE id = ? AND user_id = ?", (eid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "event not found")
    return row


def _check_times(start, end):
    try:
        s, e = parse_dt(start), parse_dt(end)
    except ValueError:
        raise HTTPException(422, "times must be ISO 8601")
    if e <= s:
        raise HTTPException(422, "end must be after start")


@app.get("/events")
def list_events(uid=Depends(user_id), conn=Depends(conn_dep)):
    return db.load_events(conn, uid)


@app.post("/events")
def add_event(body: EventIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    _check_times(body.start, body.end)
    cur = conn.execute(
        'INSERT INTO events (user_id, kind, title, start, "end", recurring) VALUES (?,?,?,?,?,?)',
        (uid, body.kind, body.title, iso(parse_dt(body.start)), iso(parse_dt(body.end)),
         json.dumps(body.recurring.model_dump()) if body.recurring else None),
    )
    return {"id": cur.lastrowid, "safety_flagged": _flag_if(conn, uid, body.title)}


@app.patch("/events/{eid}")
def patch_event(eid: int, body: EventPatch, uid=Depends(user_id), conn=Depends(conn_dep)):
    row = dict(_event_row(conn, uid, eid))
    changes = body.model_dump(exclude_unset=True)
    if "recurring" in changes:
        changes["recurring"] = json.dumps(changes["recurring"]) if changes["recurring"] else None
    row.update(changes)
    _check_times(row["start"], row["end"])
    conn.execute('UPDATE events SET kind=?, title=?, start=?, "end"=?, recurring=? WHERE id=? AND user_id=?',
                 (row["kind"], row["title"], iso(parse_dt(row["start"])), iso(parse_dt(row["end"])),
                  row["recurring"], eid, uid))
    return {"ok": True, "safety_flagged": _flag_if(conn, uid, row["title"]) if body.title else False}


@app.delete("/events/{eid}")
def delete_event(eid: int, uid=Depends(user_id), conn=Depends(conn_dep)):
    _event_row(conn, uid, eid)
    conn.execute("DELETE FROM events WHERE id = ? AND user_id = ?", (eid, uid))
    return {"ok": True}


# ---------- Google Calendar import (read-only) ----------
# The browser reads the person's calendar with a short-lived, read-only Google token and sends
# just times (and titles, if they chose to keep them). The server never sees or stores a token.

CALENDAR_SOURCE = "google"
MAX_IMPORTED_EVENT_H = 16   # longer than this is almost always an all-day or multi-day event


@app.get("/calendar/status")
def calendar_status(uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    n = conn.execute("SELECT COUNT(*) FROM events WHERE user_id = ? AND source = ?",
                     (uid, CALENDAR_SOURCE)).fetchone()[0]
    return {"imported": n, "synced_at": s.get("calendar_synced_at")}


@app.post("/calendar/import")
def calendar_import(body: CalendarImportIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    if uid == DEMO_USER:   # the demo is shared: nobody's real calendar goes into it
        raise HTTPException(409, "This is the shared demo plan, so your calendar can't go here. "
                                 "Leave the demo and sign in or set up your own plan first.")
    s = need_settings(conn, uid)
    now = now_for(s)
    clean, skipped = [], 0
    for e in body.events:
        try:
            start, end = parse_dt(e.start), parse_dt(e.end)
        except ValueError:
            skipped += 1
            continue
        if end <= start or end <= now or (end - start) > timedelta(hours=MAX_IMPORTED_EVENT_H):
            skipped += 1
            continue
        title = (e.title or "").strip() or "Busy"
        if is_flagged(title):   # never keep a flagged title; it isn't something they typed into Pace
            title = "Busy"
        clean.append((uid, "activity", title, iso(start), iso(end), None, CALENDAR_SOURCE))
    conn.execute("DELETE FROM events WHERE user_id = ? AND source = ?", (uid, CALENDAR_SOURCE))
    conn.executemany('INSERT INTO events (user_id, kind, title, start, "end", recurring, source) VALUES (?,?,?,?,?,?,?)',
                     clean)
    conn.execute("UPDATE settings SET calendar_synced_at = ? WHERE user_id = ?", (iso(now), uid))
    return {"imported": len(clean), "skipped": skipped, "synced_at": iso(now)}


@app.delete("/calendar/import")
def calendar_remove(uid=Depends(user_id), conn=Depends(conn_dep)):
    need_settings(conn, uid)
    gone = conn.execute("DELETE FROM events WHERE user_id = ? AND source = ?", (uid, CALENDAR_SOURCE)).rowcount
    conn.execute("UPDATE settings SET calendar_synced_at = NULL WHERE user_id = ?", (uid,))
    return {"removed": gone}


# ---------- tasks ----------

@app.post("/tasks/google/suggest")
def google_tasks_suggest(body: GoogleTaskSuggestIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    need_settings(conn, uid)
    if uid == DEMO_USER:
        raise HTTPException(409, "Leave the shared demo before reading your Google Tasks.")
    return {"suggestions": task_suggestions.suggest([task.model_dump() for task in body.tasks],
                                                     allow_ai=body.use_ai)}

@app.post("/tasks/google/import")
def google_tasks_import(body: GoogleTasksImportIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Import selected Google Tasks once. The browser's read-only OAuth token never reaches Pace."""
    if uid == DEMO_USER:
        raise HTTPException(409, "Leave the shared demo before importing your Google Tasks.")
    s = need_settings(conn, uid)
    now = now_for(s)
    prefs = db.load_prefs(conn, uid)
    imported = skipped = already_here = 0
    for task in body.tasks:
        try:
            due = parse_dt(task.due)
        except ValueError:
            skipped += 1
            continue
        title = task.title.strip()
        subject = task.subject.strip().lower()
        if due <= now or not title or not subject or is_flagged(title):
            skipped += 1
            continue
        planned = estimates.planned_for(task.guess_min, prefs.get(subject))
        cur = conn.execute(
            """INSERT OR IGNORE INTO tasks
               (user_id, title, subject, task_type, due, guess_min, planned_min, created_at, source, external_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (uid, title, subject, task.task_type, iso(due), task.guess_min, planned,
             iso(now), "google_tasks", task.external_id),
        )
        if cur.rowcount:
            imported += 1
        else:
            already_here += 1
    return {"imported": imported, "already_here": already_here, "skipped": skipped}

def _flag_if(conn, uid, text) -> bool:
    if is_flagged(text):
        s = db.load_settings(conn, uid)
        record_flag(conn, uid, now_for(s) if s else local_now())
        return True
    return False


def _task_row(conn, uid, tid):
    row = conn.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (tid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "task not found")
    return dict(row)


@app.get("/tasks")
def list_tasks(include_completed: bool = False, uid=Depends(user_id), conn=Depends(conn_dep)):
    return db.load_tasks(conn, uid, include_completed)


@app.post("/tasks")
def add_task(body: TaskIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    try:
        due = parse_dt(body.due)
    except ValueError:
        raise HTTPException(422, "due must be ISO 8601")
    subject = body.subject.strip().lower()
    multiplier = db.load_prefs(conn, uid).get(subject)
    planned = body.planned_min or estimates.planned_for(body.guess_min, multiplier)
    cur = conn.execute(
        """INSERT INTO tasks (user_id, title, subject, task_type, due, guess_min, planned_min, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (uid, body.title, subject, body.task_type, iso(due), body.guess_min, planned,
         iso(now_for(s))),
    )
    return {"id": cur.lastrowid, "planned_min": planned,
            "safety_flagged": _flag_if(conn, uid, body.title)}


@app.patch("/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, uid=Depends(user_id), conn=Depends(conn_dep)):
    row = _task_row(conn, uid, tid)
    row.update(body.model_dump(exclude_unset=True))
    row["due"] = iso(parse_dt(row["due"]))
    row["subject"] = row["subject"].strip().lower()
    conn.execute("""UPDATE tasks SET title=?, subject=?, task_type=?, due=?, guess_min=?, planned_min=?,
                    done_min=? WHERE id=? AND user_id=?""",
                 (row["title"], row["subject"], row["task_type"], row["due"], row["guess_min"],
                  row["planned_min"], row["done_min"], tid, uid))
    return {"ok": True, "safety_flagged": _flag_if(conn, uid, row["title"]) if body.title else False}


@app.delete("/tasks/{tid}")
def delete_task(tid: int, uid=Depends(user_id), conn=Depends(conn_dep)):
    _task_row(conn, uid, tid)
    conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (tid, uid))
    return {"ok": True}


@app.post("/tasks/{tid}/log")
def log_progress(tid: int, body: MinutesIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    """A work block ended but the task isn't finished: add the minutes to done_min."""
    _task_row(conn, uid, tid)
    conn.execute("UPDATE tasks SET done_min = done_min + ? WHERE id = ? AND user_id = ?",
                 (body.minutes, tid, uid))
    return _task_row(conn, uid, tid)


@app.post("/tasks/{tid}/finish")
def finish_task(tid: int, body: MinutesIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Body minutes = this last session. Marks done, writes one work log, returns any estimate nudge."""
    s = need_settings(conn, uid)
    t = _task_row(conn, uid, tid)
    if t["completed"]:
        raise HTTPException(409, "already finished")
    actual = max(1, t["done_min"] + body.minutes)
    now = now_for(s)
    conn.execute("UPDATE tasks SET done_min = ?, completed = 1 WHERE id = ? AND user_id = ?", (actual, tid, uid))
    conn.execute("""INSERT INTO work_logs (user_id, task_id, subject, guess_min, actual_min, logged_at)
                    VALUES (?,?,?,?,?,?)""", (uid, tid, t["subject"], t["guess_min"], actual, iso(now)))
    info = estimates.analyze(t["subject"], db.load_logs(conn, uid, t["subject"]),
                             db.load_prefs(conn, uid).get(t["subject"]))
    return {"actual_min": actual, "estimate": info}


# ---------- plan ----------

@app.get("/plan")
def get_plan(days: int = 7, weeks: bool = False, uid=Depends(user_id), conn=Depends(conn_dep)):
    """weeks=true: calendar weeks (this Monday through next Sunday). Days before today come back in
    past_days / past_nights with the sleep reported in check-ins, since the past can't be planned."""
    if not weeks:
        return context(conn, uid, days=max(1, min(days, 14)))["plan"]
    s = need_settings(conn, uid)
    today = now_for(s).date()
    monday = today - timedelta(days=today.weekday())
    ctx = context(conn, uid, days=(monday + timedelta(days=13) - today).days + 1)
    plan = ctx["plan"]
    earlier = [monday + timedelta(days=i) for i in range((today - monday).days)]
    reported = {c["date"]: c["sleep_min"] for c in db.load_checkins(conn, uid, monday.isoformat())
                if c["sleep_min"] is not None}
    plan["past_days"], plan["past_nights"] = planner.past_days(s, ctx["events"], ctx["blocked"], earlier, reported)
    plan["week_start"] = monday.isoformat()
    return plan


@app.post("/plan/rebalance")
def rebalance(uid=Depends(user_id), conn=Depends(conn_dep)):
    """Relaxed mode: daily caps +50% for the rest of this week. Never touches the sleep window."""
    s = need_settings(conn, uid)
    now = now_for(s)
    _, sunday = planner.week_bounds(now.date())
    before = context(conn, uid)["plan"]
    conn.execute("UPDATE settings SET relaxed_until = ? WHERE user_id = ?", (sunday.isoformat(), uid))
    after = context(conn, uid)["plan"]
    after["still_at_risk"] = bool(after["at_risk"])
    after["fixed_nights"] = [a["date"] for b, a in zip(before["nights"], after["nights"])
                             if b["status"] != "green" and a["status"] == "green"]
    return after


@app.delete("/plan/rebalance")
def undo_rebalance(uid=Depends(user_id), conn=Depends(conn_dep)):
    need_settings(conn, uid)
    conn.execute("UPDATE settings SET relaxed_until = NULL WHERE user_id = ?", (uid,))
    return context(conn, uid)["plan"]


# ---------- check-ins, mode ----------

@app.get("/checkins")
def list_checkins(uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    now = now_for(s)
    rows = db.load_checkins(conn, uid, (now.date() - timedelta(days=13)).isoformat())
    today = now.date().isoformat()
    return {"today": today, "needed": not any(r["date"] == today for r in rows), "checkins": rows}


@app.post("/checkins")
def save_checkin(body: CheckinIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    day = body.date or now_for(s).date().isoformat()
    conn.execute(
        """INSERT INTO checkins (user_id, date, sleep_min, energy, stress) VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, date) DO UPDATE SET sleep_min=excluded.sleep_min,
               energy=excluded.energy, stress=excluded.stress""",
        (uid, day, body.sleep_min, body.energy, body.stress),
    )
    ctx = context(conn, uid)
    return {"ok": True, "mode": ctx["mode"], "reasons": ctx["reasons"]}


@app.get("/mode")
def get_mode(uid=Depends(user_id), conn=Depends(conn_dep)):
    ctx = context(conn, uid)
    return {"mode": ctx["mode"], "reasons": ctx["reasons"]}


# ---------- coach ----------

@app.get("/coach")
def get_coach(request: Request, refresh: bool = False, uid=Depends(user_id), conn=Depends(conn_dep)):
    ctx = context(conn, uid)
    now, mode = ctx["now"], ctx["mode"]
    if mode == "safety":
        return {"mode": mode, "safety": SAFETY_SCREEN, "text": None, "source": "safety"}
    facts = coach.build_facts(mode, ctx["reasons"], ctx["plan"], ctx["tasks"], now)
    current_hash = coach.facts_hash(facts, ctx["plan"], now)
    today = now.date().isoformat()
    sent = conn.execute(
        "SELECT * FROM coach_messages WHERE user_id = ? AND sent_at >= ? AND source != 'safety' ORDER BY id DESC",
        (uid, today)).fetchall()
    if sent and sent[0]["facts_hash"] == current_hash and not refresh:
        # Reuse a message only while its next-48-hour schedule still matches.
        return {"mode": mode, "text": sent[0]["text"], "source": sent[0]["source"], "label": "AI coach"}
    schedule_changed = bool(sent and sent[0]["facts_hash"] != current_hash)
    if schedule_changed:
        # An automatic update replaces the stale message without using a manual refresh slot.
        text, source = coach.generate(mode, facts,
                                      allow_ai=not (age_gate.required() and request.state.age[0] == "child"))
        conn.execute("UPDATE coach_messages SET mode=?, text=?, source=?, sent_at=?, facts_hash=? WHERE id=?",
                     (mode, text, source, iso(now), current_hash, sent[0]["id"]))
        return {"mode": mode, "text": text, "source": source, "label": "AI coach"}
    if len(sent) >= coach.MAX_PER_DAY:
        return {"mode": sent[0]["mode"], "text": sent[0]["text"], "source": sent[0]["source"],
                "label": "AI coach", "limited": True}
    text, source = coach.generate(mode, facts,
                                  allow_ai=not (age_gate.required() and request.state.age[0] == "child"))
    conn.execute("INSERT INTO coach_messages (user_id, mode, text, source, sent_at, facts_hash) VALUES (?,?,?,?,?,?)",
                 (uid, mode, text, source, iso(now), current_hash))
    return {"mode": mode, "text": text, "source": source, "label": "AI coach"}


# ---------- decision helper ----------


@app.post("/decision/coach")
def decision_coach_chat(body: DecisionCoachIn, request: Request, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Compare choices without saving chat text or changing the plan."""
    if not body.message.strip():
        raise HTTPException(422, "Write a question for the coach.")
    if bool((body.option_a or "").strip()) != bool((body.option_b or "").strip()):
        raise HTTPException(422, "Add both options to compare them.")
    submitted = " ".join(x for x in (body.message, body.option_a, body.option_b,
                                       body.event.title if body.event else None) if x)
    if decision_coach.needs_resources(submitted):
        record_flag(conn, uid, local_now(user_id=uid))
        return {"flagged": True, "safety": SAFETY_SCREEN}
    ctx = context(conn, uid)
    if ctx["mode"] == "safety":
        return {"flagged": True, "safety": SAFETY_SCREEN}
    today = ctx["now"].date().isoformat()
    used = conn.execute("SELECT uses FROM decision_chat_usage WHERE user_id = ? AND date = ?",
                        (uid, today)).fetchone()
    if used and used["uses"] >= decision_coach.MAX_PER_DAY:
        raise HTTPException(429, "You've used today's Decide coach messages. Try again tomorrow.")

    s = ctx["settings"]
    recent = [c for c in db.load_checkins(conn, uid, (ctx["now"].date() - timedelta(days=7)).isoformat())
              if c.get("energy") is not None or c.get("sleep_min") is not None]
    last = recent[-1] if recent else {}
    nights = ctx["plan"]["nights"]
    worst = min((n["sleep_min"] for n in nights if n["sleep_min"] is not None), default=None)
    outlook = (f"{fmt_minutes(worst)} on the shortest planned night, with a {fmt_minutes(s['sleep_goal_min'])} goal"
               if worst is not None else "not available")
    event_effect = None
    if body.event:
        _check_times(body.event.start, body.event.end)
        hypo = {"id": None, "kind": body.event.kind, "title": body.event.title,
                "start": body.event.start, "end": body.event.end,
                "recurring": body.event.recurring.model_dump() if body.event.recurring else None}
        after = context(conn, uid, extra_events=[hypo])["plan"]
        losses = [max(0, b["sleep_min"] - a["sleep_min"])
                  for b, a in zip(nights, after["nights"])
                  if b["sleep_min"] is not None and a["sleep_min"] is not None]
        event_effect = {
            "largest_sleep_loss_min": max(losses, default=0),
            "new_tasks_at_risk": len([r for r in after["at_risk"]
                                      if (r["task_id"], r["title"]) not in _risk_ids(ctx["plan"])]),
            "red_nights": len([n for n in after["nights"] if n["status"] == "red"]),
        }
    facts = {"question": body.message.strip(), "option_a": (body.option_a or "").strip(),
             "option_b": (body.option_b or "").strip(), "mode": ctx["mode"],
             "energy_band": decision_coach.energy_band(last.get("energy")),
             "reported_sleep_band": decision_coach.sleep_band(last.get("sleep_min"), s["sleep_goal_min"]),
             "sleep_outlook": outlook, "event_effect": event_effect}
    allow_ai = not (age_gate.required() and request.state.age[0] == "child")
    answer, source = decision_coach.answer(facts, allow_ai=allow_ai)
    if source == "safety":
        record_flag(conn, uid, ctx["now"])
        return {"flagged": True, "safety": SAFETY_SCREEN}
    conn.execute("INSERT INTO decision_chat_usage (user_id, date, uses) VALUES (?,?,1) "
                 "ON CONFLICT(user_id, date) DO UPDATE SET uses = decision_chat_usage.uses + 1",
                 (uid, today))
    return {"flagged": False, "text": answer, "source": source,
            "energy_band": facts["energy_band"], "sleep_outlook": outlook,
            "uses_left": decision_coach.MAX_PER_DAY - (used["uses"] if used else 0) - 1}


def _risk_ids(plan):
    return {(r["task_id"], r["title"]) for r in plan["at_risk"]}


@app.post("/decision")
def decision(body: EventIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Runs the planner with and without a hypothetical event. Never saves it."""
    if _flag_if(conn, uid, body.title):
        return {"flagged": True, "safety": SAFETY_SCREEN}
    _check_times(body.start, body.end)
    before = context(conn, uid)
    hypo = {"id": None, "kind": body.kind, "title": body.title, "start": body.start, "end": body.end,
            "recurring": body.recurring.model_dump() if body.recurring else None}
    after = context(conn, uid, extra_events=[hypo])
    bp, ap = before["plan"], after["plan"]
    sleep_change = [{"date": b["date"], "before_min": b["sleep_min"], "after_min": a["sleep_min"],
                     "before_status": b["status"], "after_status": a["status"]}
                    for b, a in zip(bp["nights"], ap["nights"]) if b["sleep_min"] != a["sleep_min"]]
    newly = [r for r in ap["at_risk"] if (r["task_id"], r["title"]) not in _risk_ids(bp)]
    worst = min(n["sleep_min"] for n in ap["nights"])
    return {
        "flagged": False,
        "event": hypo,
        "before": {"nights": bp["nights"], "at_risk": bp["at_risk"], "work_hours": bp["work_hours_this_week"]},
        "after": {"nights": ap["nights"], "at_risk": ap["at_risk"], "work_hours": ap["work_hours_this_week"]},
        "sleep_change": sleep_change,
        "newly_at_risk": [{"title": r["title"], "due": r["due"], "short_by_min": r["short_by_min"]} for r in newly],
        "work_hours_after": ap["work_hours_this_week"],
        "summary_facts": {"worst_night_sleep_min": worst, "tasks_at_risk": len(ap["at_risk"]),
                          "over_15_hours": ap["work_hours_this_week"] > planner.WORK_HOURS_WARN},
    }


# ---------- "something came up" ----------

def _block_key(b):
    return (b["task_id"], b["start"], b["end"])


@app.get("/came-up")
def list_came_up(uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    now = now_for(s)
    return {"blocks": [b for b in db.load_blocked(conn, uid) if parse_dt(b["end"]) > now],
            "uses_7d": red_uses_7d(conn, uid, now)}


@app.post("/came-up")
def came_up(body: CameUpIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Red button. Never asks why."""
    s = need_settings(conn, uid)
    now = now_for(s)
    start = parse_dt(body.start) if body.start else now
    if body.rest_of_today:
        end = planner.cutoff_for(s, start.date())
        if end <= start:
            end = start + timedelta(minutes=15)
    elif body.minutes:
        end = start + timedelta(minutes=body.minutes)
    else:
        raise HTTPException(422, "give minutes or rest_of_today")

    before = context(conn, uid)
    cur = conn.execute('INSERT INTO blocked_times (user_id, start, "end", created_at) VALUES (?,?,?,?)',
                       (uid, iso(start), iso(end), iso(now)))
    after = context(conn, uid)
    bp, ap = before["plan"], after["plan"]

    after_keys = {_block_key(b) for b in ap["blocks"]}
    moved = [b for b in bp["blocks"] if _block_key(b) not in after_keys]
    shifts = [{"title": o["title"], "start": iso(o["start"]), "end": iso(o["end"])}
              for o in planner.expand_events(after["events"], start.date(), end.date())
              if o["kind"] == "shift" and o["start"] < end and o["end"] > start]
    newly = [r for r in ap["at_risk"] if (r["task_id"], r["title"]) not in _risk_ids(bp)]
    return {
        "id": cur.lastrowid, "start": iso(start), "end": iso(end),
        "moved_blocks": moved, "newly_at_risk": newly, "shifts_affected": shifts,
        "uses_7d": red_uses_7d(conn, uid, now), "plan": ap,
    }


@app.delete("/came-up/{bid}")
def undo_came_up(bid: int, uid=Depends(user_id), conn=Depends(conn_dep)):
    row = conn.execute("SELECT 1 FROM blocked_times WHERE id = ? AND user_id = ?", (bid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "block not found")
    conn.execute("DELETE FROM blocked_times WHERE id = ? AND user_id = ?", (bid, uid))
    return context(conn, uid)["plan"]


# ---------- estimates ----------

@app.get("/estimates")
def get_estimates(subject: str = None, guess_min: int = None, uid=Depends(user_id), conn=Depends(conn_dep)):
    prefs = db.load_prefs(conn, uid)
    logs = db.load_logs(conn, uid)
    subjects = sorted({l["subject"] for l in logs} | set(prefs))
    out = {"subjects": [estimates.analyze(sub, [l for l in logs if l["subject"] == sub], prefs.get(sub))
                        for sub in subjects]}
    if subject and guess_min:
        sub = subject.strip().lower()
        out["preview"] = {"subject": sub, "guess_min": guess_min, "multiplier": prefs.get(sub),
                          "planned_min": estimates.planned_for(guess_min, prefs.get(sub))}
    return out


@app.post("/estimates/{subject}/accept")
def accept_estimate(subject: str, uid=Depends(user_id), conn=Depends(conn_dep)):
    s = need_settings(conn, uid)
    sub = subject.strip().lower()
    info = estimates.analyze(sub, db.load_logs(conn, uid, sub), db.load_prefs(conn, uid).get(sub))
    if not info["suggestion"]:
        raise HTTPException(409, "no suggestion to accept")
    m = info["suggestion"]["multiplier"]
    conn.execute("""INSERT INTO estimate_prefs (user_id, subject, multiplier, accepted_at) VALUES (?,?,?,?)
                    ON CONFLICT(user_id, subject) DO UPDATE SET multiplier=excluded.multiplier,
                    accepted_at=excluded.accepted_at""", (uid, sub, m, iso(now_for(s))))
    return {"subject": sub, "multiplier": m}


# ---------- accounts (optional) ----------

def _check_new_credentials(body: AuthIn):
    if not auth.USERNAME_RE.match(body.username):
        raise HTTPException(422, "Usernames are 3 to 24 letters, numbers or underscores.")
    if len(body.password) < 8:
        raise HTTPException(422, "Use at least 8 characters for your password.")
    if body.password.lower() == body.username:
        raise HTTPException(422, "Your password can't be your username.")
    if auth.weak_password(body.password):
        raise HTTPException(422, "That password is too common. Choose a different one.")


@app.get("/auth/me")
def auth_me(uid=Depends(user_id), conn=Depends(conn_dep)):
    acct = auth.account_for_user(conn, uid)
    return {"signed_in": acct is not None, "username": acct["username"] if acct else None,
            "provider": acct["provider"] if acct else None}


@app.get("/auth/config")
def auth_config():
    """The Google client id is public (it ships in every page that shows the button)."""
    return {"google_client_id": os.environ.get("GOOGLE_CLIENT_ID") or None}


@app.post("/auth/google")
def auth_google(body: GoogleIn, request: Request, x_user_id: str = Header(None), conn=Depends(conn_dep)):
    """Sign in with Google. A known Google account gets its plan back; a new one claims the plan
    this browser already has (or a fresh one). Only Google's account number is stored."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(503, "Google sign-in isn't set up on this server yet.")
    sub = auth.verify_google_credential(body.credential, client_id)
    if not sub:
        raise HTTPException(401, "Google couldn't confirm that sign-in. Try again.")

    row = conn.execute("SELECT user_id FROM google_accounts WHERE google_sub = ?", (sub,)).fetchone()
    if row:
        uid, created = row["user_id"], False
    else:
        uid = (x_user_id or "").strip()
        if not uid or len(uid) > 64 or uid == DEMO_USER or auth.account_for_user(conn, uid):
            uid = secrets.token_hex(16)   # shared demo, or already someone's plan: start fresh
        conn.execute("INSERT INTO google_accounts (google_sub, user_id, created_at) VALUES (?,?,?)",
                     (sub, uid, iso(local_now())))
        created = True
    token = auth.create_session(conn, uid)
    return _session_cookie(JSONResponse({"user_id": uid, "username": None, "provider": "google",
                                         "created": created, "has_settings": db.load_settings(conn, uid) is not None}),
                           request, token)


@app.post("/auth/signup")
def auth_signup(body: AuthIn, request: Request, uid=Depends(user_id), conn=Depends(conn_dep)):
    """Turns this browser's plan into an account. Nothing moves: the plan keeps its id."""
    _check_new_credentials(body)
    if uid == DEMO_USER:
        raise HTTPException(409, "This is the shared demo plan, so it can't become an account. "
                                 "Set up your own plan first, then create your account.")
    if auth.account_for_user(conn, uid):
        raise HTTPException(409, "You're already signed in.")
    if conn.execute("SELECT 1 FROM accounts WHERE username = ?", (body.username,)).fetchone():
        raise HTTPException(409, "That username is taken. Try another one.")
    conn.execute("INSERT INTO accounts (user_id, username, password_hash, created_at) VALUES (?,?,?,?)",
                 (uid, body.username, auth.hash_password(body.password), iso(local_now())))
    token = auth.create_session(conn, uid)
    return _session_cookie(JSONResponse({"user_id": uid, "username": body.username}), request, token)


@app.post("/auth/login")
def auth_login(body: AuthIn, request: Request, conn=Depends(conn_dep)):
    if auth.too_many_failures(body.username):
        raise HTTPException(429, "Too many tries. Wait 15 minutes and try again.")
    row = conn.execute("SELECT * FROM accounts WHERE username = ?", (body.username,)).fetchone()
    ok = auth.verify_password(body.password, row["password_hash"] if row else auth._DUMMY_HASH)
    if not row or not ok:
        auth.record_failure(body.username)
        raise HTTPException(401, "That username and password don't match.")
    auth.clear_failures(body.username)
    has_settings = db.load_settings(conn, row["user_id"]) is not None
    token = auth.create_session(conn, row["user_id"])
    return _session_cookie(JSONResponse({"user_id": row["user_id"], "username": row["username"],
                                         "has_settings": has_settings}), request, token)


@app.post("/auth/logout")
def auth_logout(request: Request, conn=Depends(conn_dep)):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.delete_session(conn, token)
    return _clear_session_cookie(JSONResponse({"ok": True}))


@app.post("/auth/logout-all")
def auth_logout_all(request: Request, uid=Depends(user_id), conn=Depends(conn_dep)):
    if not request.cookies.get(auth.SESSION_COOKIE):
        raise HTTPException(401, "Sign in first.")
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    return _clear_session_cookie(JSONResponse({"ok": True}))


@app.post("/auth/migrate")
def auth_migrate(request: Request, authorization: str = Header(None), conn=Depends(conn_dep)):
    """One-time exchange for sessions created before cookie authentication."""
    token = _bearer(authorization)
    uid = auth.user_for_token(conn, token) if token else None
    if uid is None:
        raise HTTPException(401, "That session ended. Sign in again.")
    new_token = auth.create_session(conn, uid)
    auth.delete_session(conn, token)
    return _session_cookie(JSONResponse({"ok": True, "user_id": uid}), request, new_token)


# ---------- safety, privacy ----------

def _legal_page(filename):
    contact = (os.environ.get("PACE_CONTACT_EMAIL") or "").strip()
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", contact):
        raise HTTPException(503, "Public legal contact email is not configured")
    source = (LEGAL_TEMPLATES / filename).read_text(encoding="utf-8")
    return HTMLResponse(source.replace("{{CONTACT_EMAIL}}", html.escape(contact, quote=True)))


@app.get("/privacy-policy", response_class=HTMLResponse)
def public_privacy_policy():
    return _legal_page("privacy-policy.html")


@app.get("/terms", response_class=HTMLResponse)
def public_terms():
    return _legal_page("terms.html")


@app.get("/parent-approval", response_class=HTMLResponse)
def public_parent_approval():
    return _legal_page("parent-approval.html")


class AgeStartIn(BaseModel):
    birth_month: int
    birth_year: int


class ParentEmailIn(BaseModel):
    parent_email: str


class ParentDecisionIn(BaseModel):
    token: str


def _age_cookie(response, request, kind, uid=""):
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(age_gate.COOKIE, age_gate.sign(kind, uid), max_age=age_gate.MAX_AGE_SECONDS,
                        httponly=True, secure=secure, samesite="lax", path="/")
    return response


@app.get("/age/status")
def age_status(request: Request):
    if not age_gate.required():
        return {"required": False, "verified": True, "child": False}
    age = age_gate.read(request.cookies.get(age_gate.COOKIE))
    with db.connect() as cleanup_conn:
        age_gate.cleanup(cleanup_conn)
    if age and age[0] == "child_pending" and age[1]:
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM parent_email_consents WHERE user_id = ?", (age[1],)).fetchone()
            if not row or row["revoked_at"]:
                result = JSONResponse({"required": True, "verified": False, "child": False,
                                       "pending": True, "awaiting_parent": False, "user_id": None})
                return _age_cookie(result, request, "child_pending")
            if row and row["confirmed_at"] and not row["revoked_at"]:
                result = JSONResponse({"required": True, "verified": True, "child": True,
                                       "pending": False, "user_id": age[1]})
                return _age_cookie(result, request, "child", age[1])
            if row and row["accepted_at"] and not row["confirmation_sent_at"] and \
                    time.time() - row["accepted_at"] >= 86400:
                # The second email is delayed and sent only once; failure leaves the
                # plan locked so a later status check can retry delivery.
                token = age_gate.new_code()
                try:
                    parent_mail.send(row["parent_email"], token, confirmation=True)
                except Exception:
                    pass  # keep it pending and retry on a later check
                else:
                    conn.execute("UPDATE parent_email_consents SET confirm_token_hash = ?, "
                                 "confirmation_sent_at = ? WHERE user_id = ?",
                                 (age_gate.code_hash(token), int(time.time()), age[1]))
    if age and age[0] == "child":
        with db.connect() as conn:
            if not age_gate.approved(conn, age[1]):
                result = JSONResponse({"required": True, "verified": False, "child": False,
                                       "pending": True, "awaiting_parent": False, "user_id": None})
                return _age_cookie(result, request, "child_pending")
    return {"required": True, "verified": bool(age and age[0] in {"adult", "child"}),
            "child": bool(age and age[0] == "child"),
            "pending": bool(age and age[0] == "child_pending"),
            "awaiting_parent": bool(age and age[0] == "child_pending" and age[1]),
            "user_id": age[1] if age and age[0] == "child" else None}


@app.post("/age/start")
def age_start(body: AgeStartIn, request: Request):
    if not age_gate.required():
        return {"verified": True, "child": False}
    previous = age_gate.read(request.cookies.get(age_gate.COOKIE))
    if previous and previous[0] in {"child_pending", "child"}:
        raise HTTPException(409, "Continue the parent approval process on this browser.")
    try:
        under_13 = age_gate.is_under_13(body.birth_month, body.birth_year)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    kind = "child_pending" if under_13 else "adult"
    return _age_cookie(JSONResponse({"verified": not under_13, "child": under_13}), request, kind)


@app.post("/age/request-parent")
def request_parent(body: ParentEmailIn, request: Request, conn=Depends(conn_dep)):
    if not age_gate.required():
        raise HTTPException(404, "Age approval is not enabled")
    previous = age_gate.read(request.cookies.get(age_gate.COOKIE))
    if not previous or previous[0] != "child_pending" or previous[1]:
        raise HTTPException(403, "Start with the age screen on this browser.")
    email = body.parent_email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
        raise HTTPException(422, "Enter a valid parent email address.")
    recent = conn.execute("SELECT COUNT(*) FROM parent_email_consents "
                          "WHERE parent_email = ? AND requested_at > ?",
                          (email, int(time.time()) - 86400)).fetchone()[0]
    if recent >= 3:
        raise HTTPException(429, "Please wait before sending another request to this address.")
    uid, token = secrets.token_hex(16), age_gate.new_code()
    conn.execute("INSERT INTO parent_email_consents "
                 "(user_id, parent_email, request_token_hash, requested_at) VALUES (?,?,?,?)",
                 (uid, email, age_gate.code_hash(token), int(time.time())))
    try:
        parent_mail.send(email, token)
    except Exception as exc:
        conn.execute("DELETE FROM parent_email_consents WHERE user_id = ?", (uid,))
        raise HTTPException(503, "Could not send the parent notice. Try again later.") from exc
    return _age_cookie(JSONResponse({"pending": True, "awaiting_parent": True}), request, "child_pending", uid)


@app.delete("/age/pending")
def cancel_pending_age(request: Request, conn=Depends(conn_dep)):
    if not age_gate.required():
        raise HTTPException(404, "Age approval is not enabled")
    age = age_gate.read(request.cookies.get(age_gate.COOKIE))
    if not age or age[0] != "child_pending":
        raise HTTPException(403, "No pending parent request on this browser")
    if age[1]:
        db.delete_user(conn, age[1])
    response = JSONResponse({"ok": True})
    response.delete_cookie(age_gate.COOKIE, path="/")
    return response


@app.post("/age/parent-decision")
def parent_decision(body: ParentDecisionIn, conn=Depends(conn_dep)):
    if not age_gate.required():
        raise HTTPException(404, "Parent approval is not enabled")
    hashed = age_gate.code_hash(body.token)
    now = int(time.time())
    first = conn.execute("SELECT user_id, requested_at FROM parent_email_consents "
                         "WHERE request_token_hash = ? AND accepted_at IS NULL AND revoked_at IS NULL",
                         (hashed,)).fetchone()
    if first:
        if now - first["requested_at"] > 7 * 86400:
            conn.execute("DELETE FROM parent_email_consents WHERE user_id = ?", (first["user_id"],))
            raise HTTPException(410, "This request expired.")
        conn.execute("UPDATE parent_email_consents SET accepted_at = ? WHERE user_id = ?",
                     (now, first["user_id"]))
        return {"stage": "accepted", "message": "Consent received. Ask the child to open Pace again after a day to send the follow-up confirmation email."}
    second = conn.execute("SELECT user_id FROM parent_email_consents "
                          "WHERE confirm_token_hash = ? AND confirmed_at IS NULL AND revoked_at IS NULL",
                          (hashed,)).fetchone()
    if second:
        conn.execute("UPDATE parent_email_consents SET confirmed_at = ? WHERE user_id = ?",
                     (now, second["user_id"]))
        return {"stage": "confirmed", "message": "Confirmed. The child can reload Pace on the original browser."}
    raise HTTPException(400, "This consent link is invalid or already used.")

@app.post("/safety/check")
def safety_check(body: TextIn, uid=Depends(user_id), conn=Depends(conn_dep)):
    flagged = _flag_if(conn, uid, body.text)
    return {"flagged": flagged, "safety": SAFETY_SCREEN if flagged else None}


@app.get("/safety")
def safety_screen():
    return SAFETY_SCREEN


@app.delete("/me")
def delete_me(request: Request, uid=Depends(user_id), conn=Depends(conn_dep)):
    db.delete_user(conn, uid)
    response = JSONResponse({"ok": True})
    if age_gate.required() and request.state.age[0] == "child":
        response.delete_cookie(age_gate.COOKIE, path="/")
    return _clear_session_cookie(response)


# Static files last, so they never shadow an API route.
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="static")
