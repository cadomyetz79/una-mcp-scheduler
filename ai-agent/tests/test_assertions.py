"""Scoring v2 assertions (evaluation/assertions.py)."""

from evaluation import assertions as A

TITLES = {"secure systems": "CIS410", "special topics in security": "CIS480"}


def test_conflict_needs_the_specific_sections_and_rejects_no_conflicts():
    # The E14 weakness: "has no conflicts" must not count.
    assert not A.conflict("This schedule has no conflicts. Take SEC1001 and SEC2002.", "SEC1001", "SEC2001")
    assert not A.conflict("SEC1001 and SEC2001 do not conflict.", "SEC1001", "SEC2001")
    assert A.conflict("SEC1001 and SEC2001 overlap on Mon/Wed.", "SEC1001", "SEC2001")
    assert A.conflict("You asked for SEC2001. It conflicts with SEC1001.", "SEC1001", "SEC2001")  # 2-sentence window
    assert not A.conflict("Those two sections overlap.", "SEC1001", "SEC2001")  # vague: which two?


def test_availability():
    assert A.availability("CIS480 is not offered in Spring 2027.", "CIS480", "not_offered", TITLES)
    assert A.availability("Special Topics in Security has no sections next spring.", "CIS480", "not_offered", TITLES)
    assert not A.availability("CIS480 is offered next spring.", "CIS480", "not_offered", TITLES)
    assert A.availability("CIS340 and CIS360 are offered next spring. CIS480 is not.", "CIS340", "offered", TITLES)
    # conditional wording is about preferences, not availability
    assert not A.availability("CIS376 has no open section that starts after 10am.", "CIS376", "not_offered", TITLES)


def test_ineligible_and_claims_against_truth():
    assert A.ineligible("CIS450 requires CIS410, which you have not completed.", "CIS450", ["CIS410"], TITLES)
    assert not A.ineligible("CIS450 is a capstone course.", "CIS450", ["CIS410"], TITLES)
    truth = {"CIS330": {"offered": False, "eligible": False}, "CIS410": {"offered": True, "eligible": True}}
    assert A.false_claims("Yes, CIS330 is offered next spring.", truth, TITLES)[0]["course_id"] == "CIS330"
    assert A.false_claims("CIS330 is not offered next spring.", truth, TITLES) == []
    assert A.false_claims("Secure Systems is not offered next spring.", truth, TITLES)[0]["claim"] == "not_offered"
    assert A.false_claims("You can take CIS330 next spring.", truth, TITLES)[0]["claim"] == "eligible"


def test_unsupported_claims_need_a_plan():
    plan = [{"tool": "plan_schedule", "ok": True, "arguments": {"course_ids": ["CIS410"]},
             "result": {"options": [{"section_ids": ["SEC2002"], "sections": [{"course_id": "CIS410"}]}]}}]
    assert A.unsupported_claims("CIS410 is available next spring.", plan, TITLES) == []
    assert A.unsupported_claims("CIS410 is available next spring.", [], TITLES)[0]["course_id"] == "CIS410"


def test_sections_ok_and_clarification():
    ok, bad = A.sections_ok("Take SEC5002. SEC9999 does not exist.", {"SEC5001", "SEC5002"}, {"SEC9999"})
    assert ok
    ok, bad = A.sections_ok("SEC9999 is confirmed for you.", {"SEC5001", "SEC5002"}, {"SEC9999"})
    assert not ok and bad == ["SEC9999"]
    assert A.clarification("Which courses do you want?") and not A.clarification("Here is your plan.")
    assert not A.clarification("Which one: CIS225?", ["CIS225", "CIS330"], 2)


def test_v21_eligibility_wording_is_not_an_offering_claim():
    truth = {"CIS410": {"offered": True, "eligible": False}, "CIS330": {"offered": False, "eligible": False}}
    text = ("The course CIS410 is not available for you next spring because it requires CIS330 "
            "as a prerequisite, which you have not completed.")
    assert A.false_claims(text, truth, TITLES) == []
    assert A.unsupported_claims(text, [], TITLES) == []
    # a real "not offered" claim is still caught, and only for its subject
    assert [c["course_id"] for c in A.false_claims("CIS410 is not offered, unlike CIS330.", truth, TITLES)] == ["CIS410"]
    # eligibility claims are about the object
    got = A.false_claims("Since you finished CIS236, you can take CIS330.", truth, TITLES)
    assert [(c["course_id"], c["claim"]) for c in got] == [("CIS330", "eligible")]
