from datetime import datetime

import pytest

from backend import coach
from backend.safety import FLAG_PHRASES, is_flagged


@pytest.mark.parametrize("phrase", FLAG_PHRASES)
def test_every_phrase_flags_any_case_with_punctuation(phrase):
    assert is_flagged(phrase)
    assert is_flagged(phrase.upper())
    assert is_flagged(f"honestly... {phrase.title()}!!!")


def test_normal_text_is_fine():
    for text in ["Chem lab report", "History essay", "I want to spend it all on shoes",
                 "Cut the onions for dinner", "Kill the lights at 10"]:
        assert not is_flagged(text)


class FakeClient:
    """Stands in for anthropic.Anthropic; records what it was sent."""

    def __init__(self, reply="Tonight: Chem lab report. Stop by 9:45 PM."):
        self.reply, self.calls = reply, []
        outer = self

        class Messages:
            def create(self, **kwargs):
                outer.calls.append(kwargs)

                class Block:
                    type = "text"
                    text = outer.reply

                class Resp:
                    stop_reason = "end_turn"
                    content = [Block()]
                return Resp()

        class Beta:
            messages = Messages()
        self.beta = Beta()


def plan_with(title):
    return {"blocks": [{"title": title, "minutes": 45, "start": "2026-10-19T19:00:00",
                        "end": "2026-10-19T19:45:00"}],
            "stop_time": "2026-10-19T21:45:00", "days": [{"date": "2026-10-19", "events": [], "blocked": []}]}


def test_flagged_text_never_reaches_ai():
    tasks = [{"title": "i want to die", "due": "2026-10-20T08:00:00", "completed": 0}]
    facts = coach.build_facts("steady", [], plan_with("i want to die"), tasks, datetime(2026, 10, 19, 15, 0))
    client = FakeClient()
    coach.generate("steady", facts, client=client)
    sent = str(client.calls)
    assert "want to die" not in sent
    assert "a task" in sent


def test_safety_mode_never_calls_ai():
    client = FakeClient()
    with pytest.raises(ValueError):
        coach.generate("safety", {}, client=client)
    assert client.calls == []


def test_flagged_ai_output_replaced_by_fallback():
    facts = coach.build_facts("steady", [], plan_with("Chem lab report"), [], datetime(2026, 10, 19, 15, 0))
    text, source = coach.generate("steady", facts, client=FakeClient(reply="Honestly you could just end it all."))
    assert source == "fallback"
    assert text == "Tonight: Chem lab report (45 min). Stop by 9:45 PM to protect your sleep."


def test_ai_text_used_when_clean():
    facts = coach.build_facts("steady", [], plan_with("Chem lab report"), [], datetime(2026, 10, 19, 15, 0))
    text, source = coach.generate("steady", facts, client=FakeClient())
    assert source == "ai" and "9:45 PM" in text


def test_coach_rejects_clear_schedule_claim_when_tasks_are_planned():
    facts = coach.build_facts("steady", [], plan_with("Chem lab report"), [],
                              datetime(2026, 10, 19, 15, 0))
    text, source = coach.generate("steady", facts, client=FakeClient(reply="Nothing is scheduled in the next 48 hours."))
    assert source == "fallback" and "Chem lab report" in text


def test_fallbacks_use_12_hour_time():
    facts = {"tonight": [{"title": "Chem", "minutes": 45}], "stop_time": "9:45 PM",
             "deadlines_next_48h": [{"title": "Chem", "due": "Tue 8:00 AM"}], "next_task": "Essay"}
    assert coach.fallback_message("recovery", facts) == (
        "You've been short on sleep. Just Chem tonight, then stop at 9:45 PM. Everything else can wait.")
    assert coach.fallback_message("steady", {"tonight": [], "deadlines_next_48h": [],
                                             "stop_time": "9:45 PM"}) == "Nothing due soon. Rest up."
    # Recovery with nothing planned tonight never tells them to work tonight.
    assert coach.fallback_message("recovery", {**facts, "tonight": []}) == (
        "You've been short on sleep. Nothing is planned tonight, so rest. Chem is next, due Tue 8:00 AM.")
