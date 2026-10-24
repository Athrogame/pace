"""Keyword safety filter.

A keyword list will miss things and sometimes over-trigger. A false alarm only
shows a supportive screen, so we lean toward catching more."""
import re

FLAG_PHRASES = [
    "kill myself", "killing myself", "want to die", "wanna die", "suicide", "suicidal",
    "end my life", "end it all", "hurt myself", "hurting myself", "self harm", "self-harm",
    "cut myself", "cutting myself", "no reason to live", "better off without me",
    "better off dead", "don't want to be here", "dont want to be here",
]

SAFETY_SCREEN = {
    "title": "You don't have to handle this alone.",
    "lines": [
        "If you're thinking about hurting yourself, please reach out now.",
        "Call or text 988 (Suicide & Crisis Lifeline, 24/7, free).",
        "If you're in immediate danger, call 911.",
        "Talking to a parent, school counselor or another trusted adult can help too.",
    ],
    "call": "tel:988",
    "text": "sms:988",
}


def normalize(text: str) -> str:
    """lowercase, drop apostrophes (don't -> dont), every other non-letter becomes a space."""
    text = (text or "").lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " " + " ".join(text.split()) + " "


# Common run-together spellings, matched as whole-word starts like everything else.
RUN_TOGETHER = ["selfharm", "killmyself", "hurtmyself", "cutmyself", "wanttodie", "kms"]

_NORMALIZED = sorted({normalize(p).strip() for p in FLAG_PHRASES} | set(RUN_TOGETHER))


def is_flagged(text: str) -> bool:
    clean = normalize(text)
    # Word start, open end: "suicide" also catches "suicides".
    return any(" " + phrase in clean for phrase in _NORMALIZED if phrase != "kms") \
        or " kms " in clean
