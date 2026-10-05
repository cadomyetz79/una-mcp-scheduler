"""Scenario tests against the team's real mock dataset in data/*.json.

Each test documents an expected outcome for the research paper:
which proposed schedule, which rule, and what the validator returned.
"""

from scheduling.validators import validate_schedule

TERM = "2027SP"


def codes(result):
    return sorted(i.code for i in result.issues)


def run(ds, student_id, section_ids, term=TERM):
    return validate_schedule(
        ds.students[student_id], section_ids, term, ds.sections, ds.courses
    )


def test_valid_schedule_in_person_plus_online(ds):
    # S10001 completed CIS330 -> eligible for CIS376 and CIS410.
    r = run(ds, "S10001", ["SEC1001", "SEC2002"])
    assert r.valid, r.to_dict()
    assert r.total_credit_hours == 6


def test_time_conflict_mon_wed(ds):
    # SEC1001 MON/WED 09:30-10:45 vs SEC2001 MON/WED 10:30-11:45
    r = run(ds, "S10001", ["SEC1001", "SEC2001"])
    assert codes(r) == ["TIME_CONFLICT"]


def test_full_section_rejected(ds):
    # SEC1002 is 30/30
    r = run(ds, "S10001", ["SEC1002"])
    assert codes(r) == ["SECTION_FULL"]


def test_capstone_missing_both_prerequisites(ds):
    # CIS450 requires CIS376 AND CIS410; S10001 has neither.
    r = run(ds, "S10001", ["SEC3001"])
    assert codes(r) == ["MISSING_PREREQUISITE"]
    assert set(r.issues[0].course_ids) == {"CIS450", "CIS376", "CIS410"}


def test_prerequisite_missing_for_other_student(ds):
    # S10002 completed CIS236 but not CIS330 -> not eligible for CIS376.
    r = run(ds, "S10002", ["SEC1001"])
    assert codes(r) == ["MISSING_PREREQUISITE"]


def test_failed_course_does_not_count(ds):
    # S10003 failed CIS236 and is inactive.
    student = ds.students["S10003"]
    assert "CIS236" not in student.completed_courses
    r = run(ds, "S10003", ["SEC2002"])
    assert "STUDENT_INACTIVE" in codes(r)
    assert "MISSING_PREREQUISITE" in codes(r)


def test_two_sections_of_same_course(ds):
    r = run(ds, "S10001", ["SEC2001", "SEC2002"])
    assert "DUPLICATE_COURSE" in codes(r)


def test_unknown_section(ds):
    r = run(ds, "S10001", ["SEC9999"])
    assert codes(r) == ["UNKNOWN_SECTION"]
    assert not r.valid


def test_wrong_term(ds):
    r = run(ds, "S10001", ["SEC2002"], term="2026FA")
    assert codes(r) == ["WRONG_TERM"]


def test_result_is_json_friendly(ds):
    import json

    r = run(ds, "S10001", ["SEC1001", "SEC2001"])
    payload = json.dumps(r.to_dict())
    assert "TIME_CONFLICT" in payload
