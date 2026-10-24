"""Mode engine. Checked top to bottom; first match wins.
The AI never decides the mode; these rules do."""

SAFETY, RECOVERY, STEADY, PUSH = "safety", "recovery", "steady", "push"


def _get(c, key):
    return c.get(key) if isinstance(c, dict) else getattr(c, key, None)


def pick_mode(checkins, sleep_goal_min, red_button_uses_7d=0, safety_flag_recent=False,
              week_has_slack=False):
    """checkins: oldest to newest, only days that have data."""
    last3 = checkins[-3:]

    # SAFETY
    if safety_flag_recent:
        return SAFETY, ["safety filter flagged a message"]
    if len(last3) == 3 and all(_get(c, "stress") == 5 and _get(c, "energy") == 1 for c in last3):
        return SAFETY, ["very low check-ins 3 days in a row"]

    # RECOVERY
    sleep_debt = sum(max(0, sleep_goal_min - _get(c, "sleep_min"))
                     for c in last3 if _get(c, "sleep_min"))
    last2 = checkins[-2:]
    today = checkins[-1] if checkins else None
    reasons = []
    if sleep_debt >= 180:
        reasons.append(f"sleep debt {sleep_debt} min over 3 nights")
    if len(last2) == 2 and all((_get(c, "stress") or 0) >= 4 for c in last2):
        reasons.append("stress 4+ two days running")
    if today and _get(today, "energy") is not None and _get(today, "energy") <= 2:
        reasons.append("energy 2 or lower today")
    if red_button_uses_7d >= 3:
        reasons.append("red button used 3+ times this week")
    if reasons:
        return RECOVERY, reasons

    # PUSH
    if (len(last3) == 3
            and all(_get(c, "sleep_min") and _get(c, "sleep_min") >= sleep_goal_min for c in last3)
            and today and (_get(today, "stress") or 5) <= 2 and (_get(today, "energy") or 0) >= 4
            and week_has_slack):
        return PUSH, ["rested, low stress, open time this week"]

    return STEADY, []
