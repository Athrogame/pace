"""Learning estimates from a student's own completed work.

Weighted-average statistics on the user's own logs, not a trained model. Recent
tasks count more, single ratios are clamped, and nothing changes until the user
taps Accept."""

HISTORY = 10
DECAY = 0.8
CLAMP_LO, CLAMP_HI = 0.25, 8.0
NOTE_HI, NOTE_LO = 2.0, 0.5
DRIFT = 0.25


def _ratio(log) -> float:
    guess = max(1, log["guess_min"])
    return max(CLAMP_LO, min(CLAMP_HI, log["actual_min"] / guess))


def subject_ratio(logs) -> float:
    """logs sorted newest first."""
    logs = logs[:HISTORY]
    if not logs:
        return 1.0
    weights = [DECAY ** i for i in range(len(logs))]
    ratios = [_ratio(l) for l in logs]
    return sum(w * r for w, r in zip(weights, ratios)) / sum(weights)


def round15(minutes: float) -> int:
    return max(15, int(round(minutes / 15.0)) * 15)


def fmt_multiplier(m: float) -> str:
    m = round(m, 1)
    return f"{int(m)}×" if m == int(m) else f"{m}×"


def analyze(subject: str, logs, accepted=None) -> dict:
    """What to say about one subject. logs newest first."""
    logs = logs[:HISTORY]
    n = len(logs)
    ratio = subject_ratio(logs) if logs else None
    out = {"subject": subject, "logs": n, "ratio": round(ratio, 2) if ratio else None,
           "accepted_multiplier": accepted, "note": None, "suggestion": None}
    if n == 0:
        return out
    if n < 3:
        latest = _ratio(logs[0])
        if latest > NOTE_HI or latest < NOTE_LO:
            out["note"] = f"That took about {fmt_multiplier(latest)} your guess."
        return out
    base = accepted or 1.0
    if ratio / base > 1 + DRIFT or ratio / base < 1 - DRIFT:
        suggested = round(ratio, 1)
        out["suggestion"] = {
            "multiplier": suggested,
            "text": (f"{subject.capitalize()} usually takes you about {fmt_multiplier(suggested)} "
                     f"your guess. Use that for new {subject} tasks?"),
        }
    return out


def planned_for(guess_min: int, multiplier=None) -> int:
    if not multiplier:
        return guess_min
    return round15(guess_min * multiplier)
