"""Google Tasks suggestions remain reviewable and safe when the AI fails."""
import json
from types import SimpleNamespace

from backend import task_suggestions


def test_local_guesses_handle_common_school_shorthand(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    guesses = task_suggestions.suggest([
        {"title": "study algebra", "list_title": "My Tasks"},
        {"title": "euro hw", "list_title": "My Tasks"},
        {"title": "buy milk", "list_title": "My Tasks"},
    ])
    assert guesses[0] == {"subject": "math", "task_type": "test_study", "guess_min": 60, "source": "estimate"}
    assert guesses[1] == {"subject": "history", "task_type": "homework", "guess_min": 30, "source": "estimate"}
    assert guesses[2]["subject"] == "general"


def test_ai_suggestions_are_validated_and_flagged_titles_stay_local():
    class FakeMessages:
        def create(self, **kwargs):
            sent = json.loads(kwargs["messages"][0]["content"])
            assert [item["index"] for item in sent] == [0, 2]
            content = json.dumps({"suggestions": [
                {"index": 0, "subject": "math", "task_type": "homework", "guess_min": 45},
                {"index": 1, "subject": "math", "task_type": "homework", "guess_min": 45},
                {"index": 2, "subject": "history", "task_type": "homework", "guess_min": 999},
            ]})
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=content)])

    guesses = task_suggestions.suggest([
        {"title": "algebra worksheet", "list_title": "School"},
        {"title": "I want to die", "list_title": "School"},
        {"title": "euro hw", "list_title": "School"},
    ], client=SimpleNamespace(messages=FakeMessages()))
    assert guesses[0] == {"subject": "math", "task_type": "homework", "guess_min": 45, "source": "ai"}
    assert guesses[1]["source"] == "estimate"
    assert guesses[2]["guess_min"] == 30 and guesses[2]["source"] == "estimate"


def test_without_ai_does_not_call_provider():
    class NeverCall:
        def create(self, **_kwargs):
            raise AssertionError("AI provider should not be called")

    result = task_suggestions.suggest([{"title": "algebra homework", "list_title": "My Tasks"}],
                                      client=SimpleNamespace(messages=NeverCall()), allow_ai=False)
    assert result[0]["subject"] == "math" and result[0]["source"] == "estimate"
