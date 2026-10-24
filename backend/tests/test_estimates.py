from backend.estimates import analyze, planned_for, round15, subject_ratio


def log(guess, actual):
    return {"guess_min": guess, "actual_min": actual}


def test_one_log_at_6x_gives_note_not_suggestion():
    info = analyze("math", [log(30, 180)])
    assert info["note"] == "That took about 6× your guess."
    assert info["suggestion"] is None


def test_three_logs_at_3x_suggest_3x():
    info = analyze("math", [log(30, 90), log(20, 60), log(40, 120)])
    assert info["suggestion"]["multiplier"] == 3.0
    assert "about 3×" in info["suggestion"]["text"]


def test_ratios_clamp():
    assert subject_ratio([log(10, 1000)]) == 8.0
    assert subject_ratio([log(100, 1)]) == 0.25


def test_recent_logs_weigh_more():
    newest_slow = subject_ratio([log(10, 40), log(10, 10), log(10, 10)])
    newest_fast = subject_ratio([log(10, 10), log(10, 10), log(10, 40)])
    assert newest_slow > newest_fast


def test_good_guesses_say_nothing():
    info = analyze("english", [log(30, 33), log(30, 28), log(30, 30)])
    assert info["note"] is None and info["suggestion"] is None


def test_nothing_changes_until_accept():
    assert planned_for(30, None) == 30          # no accepted multiplier: plan the guess
    assert planned_for(30, 3.0) == 90
    assert round15(37) == 30 and round15(38) == 45


def test_drift_from_accepted_multiplier():
    logs = [log(30, 90)] * 3
    assert analyze("math", logs, accepted=3.0)["suggestion"] is None
    assert analyze("math", [log(30, 150)] * 3, accepted=3.0)["suggestion"]["multiplier"] == 5.0
