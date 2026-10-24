"""AI coach. The mode engine decides push vs. rest; the AI only
writes the wording. Every failure path lands on a fixed fallback message."""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta

from .safety import is_flagged
from .timeutil import fmt_day, fmt_minutes, fmt_time, parse_dt

MAX_PER_DAY = 3
TIMEOUT_S = 5.0
MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")

SYSTEM_PROMPT = """You are Pace, an AI planning coach inside a student planning app. You are not a person,
a friend, a therapist or a counselor. If asked, say clearly that you are an AI.

Write ONE message under 60 words for the student, based only on the JSON facts given.
Never invent tasks, times, numbers or deadlines. Write times exactly as given (12-hour with AM/PM).
If a block or deadline appears in the next 48 hours, never say the schedule is clear.

Modes:
- push: encourage a small, specific stretch goal from the facts.
- steady: walk through tonight's plan in order.
- recovery: tell them to do only what's due soon, name the stop time, and encourage rest.

Never: diagnose, give medical or mental health treatment advice, talk about your feelings,
use romantic or "I'm always here for you" language, or encourage skipping sleep.
If the student seems to be having a hard time, suggest talking to a friend, parent,
or school counselor.

Tone: direct, warm, plain words, like a good coach. No emoji."""

FALLBACK = {
    "push": "You're rested and ahead. Want to start {next_task} tonight and get a head start on next week?",
    "steady": "Tonight: {task_list}. Stop by {stop_time} to protect your sleep.",
    "recovery": "You've been short on sleep. Just {urgent_task} tonight, then stop at {stop_time}. Everything else can wait.",
}
NOTHING_DUE = "Nothing due soon. Rest up."


def _safe_title(title: str) -> str:
    """Anything the safety filter flags never goes to the AI."""
    return "a task" if is_flagged(title) else title


def build_facts(mode: str, reasons: list, plan: dict, tasks: list, now: datetime) -> dict:
    today = now.date().isoformat()
    tonight = {}
    for b in plan["blocks"]:
        if b["start"].startswith(today) and parse_dt(b["end"]) > now:
            title = _safe_title(b["title"])
            tonight[title] = tonight.get(title, 0) + b["minutes"]
    soon = now + timedelta(hours=48)
    open_tasks = sorted((t for t in tasks if not t.get("completed")), key=lambda t: t["due"])
    deadlines = [{"title": _safe_title(t["title"]), "due": fmt_day(t["due"])}
                 for t in open_tasks if parse_dt(t["due"]) <= soon]
    later = [t for t in open_tasks if parse_dt(t["due"]) > soon]
    today_days = [d for d in plan["days"] if d["date"] == today]
    work_tonight = bool(today_days and any(e["kind"] == "shift" for e in today_days[0]["events"]))
    scheduled = [{"title": _safe_title(b["title"]), "start": fmt_day(b["start"]),
                  "minutes": b["minutes"]}
                 for b in plan["blocks"]
                 if parse_dt(b["start"]) < soon and parse_dt(b["end"]) > now]
    busy = [{"kind": e["kind"], "start": fmt_day(e["start"]), "end": fmt_day(e["end"])}
            for day in plan["days"] for e in day["events"]
            if parse_dt(e["start"]) < soon and parse_dt(e["end"]) > now]
    unavailable = [{"start": fmt_day(b["start"]), "end": fmt_day(b["end"])}
                   for day in plan["days"] for b in day["blocked"]
                   if parse_dt(b["start"]) < soon and parse_dt(b["end"]) > now]
    return {
        "mode": mode,
        "tonight": [{"title": k, "minutes": v} for k, v in tonight.items()],
        "stop_time": fmt_time(plan["stop_time"]),
        "deadlines_next_48h": deadlines,
        "next_task": _safe_title(later[0]["title"]) if later else None,
        "work_tonight": work_tonight,
        "scheduled_next_48h": scheduled,
        "busy_next_48h": busy,
        "unavailable_next_48h": unavailable,
    }


def facts_hash(facts: dict, plan: dict, now: datetime) -> str:
    """Key the message to visible facts and event edits without sending event names to AI."""
    soon = now + timedelta(hours=48)
    event_details = [{"kind": e["kind"], "title": e["title"],
                      "start": e["start"], "end": e["end"]}
                     for day in plan["days"] for e in day["events"]
                     if parse_dt(e["start"]) < soon and parse_dt(e["end"]) > now]
    encoded = json.dumps({"facts": facts, "event_details": event_details},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fallback_message(mode: str, facts: dict) -> str:
    tonight = facts.get("tonight") or []
    upcoming = facts.get("scheduled_next_48h") or []
    if mode == "push":
        if not facts.get("next_task"):
            if tonight:
                return FALLBACK["steady"].format(task_list=_list(tonight), stop_time=facts["stop_time"])
            return f"Next up: {upcoming[0]['title']} at {upcoming[0]['start']}." if upcoming else NOTHING_DUE
        return FALLBACK["push"].format(next_task=facts["next_task"])
    if mode == "recovery":
        if tonight:
            return FALLBACK["recovery"].format(urgent_task=tonight[0]["title"], stop_time=facts["stop_time"])
        if facts.get("deadlines_next_48h"):
            nxt = facts["deadlines_next_48h"][0]
            return (f"You've been short on sleep. Nothing is planned tonight, so rest. "
                    f"{nxt['title']} is next, due {nxt['due']}.")
        if upcoming:
            return f"Rest tonight. Next up: {upcoming[0]['title']} at {upcoming[0]['start']}."
        return NOTHING_DUE
    if not tonight:
        if upcoming:
            return f"Next up: {upcoming[0]['title']} at {upcoming[0]['start']}."
        if not facts.get("deadlines_next_48h"):
            return NOTHING_DUE
        return f"Nothing planned tonight. Stop by {facts['stop_time']} to protect your sleep."
    return FALLBACK["steady"].format(task_list=_list(tonight), stop_time=facts["stop_time"])


def _list(tonight) -> str:
    parts = [f"{t['title']} ({fmt_minutes(t['minutes'])})" for t in tonight]
    if len(parts) <= 2:
        return " then ".join(parts)
    return ", ".join(parts[:-1]) + ", then " + parts[-1]


def _api_key():
    return os.environ.get("AI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


def call_ai(facts: dict, client=None):
    """Returns the AI's text, or None on any failure. `client` lets tests inject a fake."""
    if client is None:
        key = _api_key()
        if not key:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, max_retries=0)
        except Exception:
            return None
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(facts)}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except Exception:
        return None
    if getattr(response, "stop_reason", None) == "refusal":
        return None
    text = " ".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
    return text or None


def generate(mode: str, facts: dict, client=None, allow_ai=True):
    """(text, source). Safety mode never reaches here: the route shows the safety screen."""
    if mode == "safety":
        raise ValueError("safety mode never calls the coach")
    text = call_ai(facts, client=client) if allow_ai else None
    claims_empty = bool(text and re.search(
        r"\b(?:nothing (?:is )?(?:scheduled|planned|due)|no (?:tasks?|work|deadlines?) (?:are )?due|plan is clear)\b",
        text, re.I))
    has_upcoming = bool(facts.get("scheduled_next_48h") or facts.get("deadlines_next_48h"))
    if text and not is_flagged(text) and not (claims_empty and has_upcoming):
        return text, "ai"
    return fallback_message(mode, facts), "fallback"
