from backend.modes import pick_mode

GOAL = 510


def c(sleep=510, energy=3, stress=3):
    return {"sleep_min": sleep, "energy": energy, "stress": stress}


def test_no_checkins_is_steady():
    assert pick_mode([], GOAL) == ("steady", [])


def test_safety_from_flag():
    assert pick_mode([c()], GOAL, safety_flag_recent=True)[0] == "safety"


def test_safety_from_three_very_low_days():
    assert pick_mode([c(energy=1, stress=5)] * 3, GOAL)[0] == "safety"
    assert pick_mode([c(energy=1, stress=5)] * 2, GOAL)[0] == "recovery"  # only 2 days: not safety


def test_recovery_triggers():
    assert pick_mode([c(sleep=400), c(sleep=420), c()], GOAL)[0] == "recovery"   # 200 min debt
    assert pick_mode([c(stress=4), c(stress=5)], GOAL)[0] == "recovery"
    assert pick_mode([c(energy=2)], GOAL)[0] == "recovery"
    assert pick_mode([c()], GOAL, red_button_uses_7d=3)[0] == "recovery"


def test_push_needs_everything():
    rested = [c(sleep=520, energy=4, stress=2)] * 3
    assert pick_mode(rested, GOAL, week_has_slack=True)[0] == "push"
    assert pick_mode(rested, GOAL, week_has_slack=False)[0] == "steady"
    assert pick_mode(rested[:2], GOAL, week_has_slack=True)[0] == "steady"


def test_priority_safety_beats_recovery_beats_push():
    tired = [c(sleep=300, energy=4, stress=2)] * 3
    assert pick_mode(tired, GOAL, safety_flag_recent=True, week_has_slack=True)[0] == "safety"
    assert pick_mode(tired, GOAL, week_has_slack=True)[0] == "recovery"


def test_missing_values_dont_crash():
    assert pick_mode([{"sleep_min": None, "energy": None, "stress": None}] * 3, GOAL)[0] == "steady"
