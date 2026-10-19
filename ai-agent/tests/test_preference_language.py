"""Rule-based reading of preference strength (agent/preference_language.py).

These phrasings are NOT the evaluation requests, so they give a small
independent check of the cue lists. They were still written by the same
author, so they are not a substitute for real student wording.
"""

import pytest

from agent.preference_language import classify, reconcile


@pytest.mark.parametrize("text, group, verdict", [
    ("I'd rather not start before 9am.", "time", "soft"),
    ("Mornings would be nice to avoid if you can.", "time", "soft"),
    ("Hopefully I can finish by 2pm.", "time", "soft"),
    ("Preferably no Tuesday classes.", "days", "soft"),
    ("I have to be done by 1pm for my job.", "time", "required"),
    ("I must not have anything on Thursdays.", "days", "required"),
    ("I'm unable to attend on weekends.", "days", "required"),
    ("No classes before 10.", "time", "unknown"),          # no strength cue
    ("I don't want Friday classes.", "days", "unknown"),    # no strength cue
    ("Ideally after 10am, but I really can't do 8am.", "time", "unknown"),  # mixed
])
def test_classify(text, group, verdict):
    assert classify(text)[group]["verdict"] == verdict


def test_cues_are_tied_to_the_clause_about_the_preference():
    r = classify("I need CIS376 and CIS410. If possible I'd like no classes before 10am.")
    assert r["time"]["verdict"] == "soft"  # "need" is about the courses, not the time
    r = classify("I can't do Fridays at all, and I'd prefer to start after 10am.")
    assert (r["days"]["verdict"], r["time"]["verdict"]) == ("required", "soft")


def test_reconcile_only_changes_clear_cases():
    req, fixes = reconcile("I'd prefer no classes before 10am if possible.", ["earliest_start"], ["earliest_start"])
    assert req == [] and fixes[0]["model_said"] == "required"
    req, fixes = reconcile("I cannot come on Mondays.", ["avoid_days"], [])
    assert req == ["avoid_days"] and fixes[0]["applied"] == "required"
    req, fixes = reconcile("No classes before 10.", ["earliest_start"], ["earliest_start"])
    assert req == ["earliest_start"] and fixes == []  # ambiguous: model's choice stands
    req, fixes = reconcile("I'd prefer no classes before 10am.", [], ["earliest_start"])
    assert req == ["earliest_start"] and fixes == []  # preference not stated: nothing to correct
