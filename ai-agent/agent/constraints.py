"""Deterministic reading of the time and day constraints a student states.

Why (integration-readiness audit 2026-10-19, defect D4): the model fills in
plan_schedule's earliest_start / latest_end / avoid_days. Before this module
code checked only HOW STRONGLY a preference was stated
(preference_language.py), and only for preferences the model passed:
- a constraint the model left out ("I can't do Fridays", no avoid_days) was
  never applied, so options with Friday classes came back as valid;
- a wrong value ("done by 3pm" -> latest_end "13:00" or "16:00") was applied
  as given;
- wording the strength check does not link to a preference ("between 10am
  and 3pm", "nothing after 5", "before noon") made unmentioned() drop the
  model's values, even correct ones.

What this module does, from the student's words only (no model):

1. extract(): per preference, the value the student stated, whether it could
   be read RELIABLY, and how strongly it was stated (same cues and lending as
   preference_language.py, but linked by the value rules below).
     earliest_start  "nothing before 10am", "start after 9:30", "not before
                     noon", "I work until 11", "my shift ends at 10"
     latest_end      "done by 3pm", "out before 4:30", "nothing after 5",
                     "no later than 2", "I can stay until 4",
                     "my shift starts at 1pm"
     both            "between 10am and 3pm", "from 9 to 2", "10am-3pm"
     avoid_days      "I can't do Fridays", "no classes Mon or Wed", "keep
                     Fridays free", "I work Tuesdays", "no weekends",
                     "Mondays and Wednesdays only" (= every other day)
   Not reliable, so never guessed: vague words without a time ("mornings",
   "late"), an hour that could be AM or PM, a time not tied to a start or an
   end ("10am is a problem"), a limit for some days only ("Monday mornings",
   "Fridays after 3pm" - the planner applies time limits to every day), busy
   time ranges ("I work from 8 to 10"), day ranges ("Monday to Thursday"), a
   day with no direction ("Fridays."), different values for one preference.

2. resolve(): combines that reading with the model's plan_schedule arguments.
     required + reliable    the student's value is applied as mandatory,
                            also when the model left it out or got it wrong
     required + unreliable  ClarificationNeeded: no schedule is built, the
                            student is asked a fixed question
     other + reliable       the student's value replaces a different or
                            missing model value; the strength stays the
                            model's. If the model left the preference out:
                            mandatory when the student stated it without any
                            softening or relaxing words ("No Friday
                            classes.", "nothing ending after 5pm"), soft
                            otherwise
     other + unreliable     the model's value stands
   Every change is listed (Resolution.changes) and reported in the tool
   result.

3. system_arguments(): the preference arguments for the evidence-check
   recovery, so the assistant can run plan_schedule itself when every stated
   constraint was read reliably (before, it never ran when the request
   mentioned times or days).

Times without AM/PM (WORKING ASSUMPTION, classes run between about 8:00 and
21:00): 13-23 are 24-hour times and 12 is noon; for a start, 7-11 are AM and
1-6 are PM; for an end, 1-9 are PM. An end at 10 or 11 without AM/PM is
ambiguous. Starts must be 07:00-18:00 and ends 09:00-23:00 to be used.

Limits (WORKING ASSUMPTION): English only, keyword based, written and tested
by the project team, not validated on real student wording. The rules were
checked against the request texts of every dataset, including heldout2's
(read only, never run); see docs/workstream3-integration-audit.md, D4. The module never
decides schedule validity (the planner and validate_schedule do), and it
never makes a constraint looser than the student's clear words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .preference_language import _COURSE, PREFS, _targets, fragments

TIME_PREFS = ("earliest_start", "latest_end")
WEEK = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_DAY_WORDS = {
    "MON": r"mon(?:day)?s?", "TUE": r"tue(?:s(?:day)?)?s?", "WED": r"wed(?:nesday)?s?",
    "THU": r"thu(?:r(?:s(?:day)?)?)?s?", "FRI": r"fri(?:day)?s?", "SAT": r"sat(?:urday)?s?",
    "SUN": r"sun(?:day)?s?",
}
_ANY_DAY = r"(?:" + "|".join(_DAY_WORDS.values()) + r")"
_DAY = re.compile(r"\b(?:" + "|".join(f"(?P<{d}>{p})" for d, p in _DAY_WORDS.items()) + r")\b", re.I)
_WEEKEND = re.compile(r"\bweekends?\b", re.I)
_DAY_RANGE = re.compile(rf"\b{_ANY_DAY}\s*(?:through|thru|to|until|till|-|–)\s*{_ANY_DAY}\b", re.I)

# One time of day. Not inside IDs, dates or decimals; not a count ("3 courses").
_UNITS = r"(?:courses?|classes?|credits?|credit|sections?|hours?|hrs?|units?|days?|weeks?|times?|semesters?|terms?|more|of)"
_TIME_RE = (r"(?<![\w:.\-/])(?:(?P<h{n}>\d{{1,2}})(?::(?P<m{n}>[0-5]\d))?\s*(?P<ap{n}>a\.m\.|p\.m\.|am\b|pm\b)?"
            r"(?![\d:.\-/])(?!\s*" + _UNITS + r"\b)|(?P<noon{n}>noon|midday)\b)")


def _t(n: str = "") -> str:
    return _TIME_RE.format(n=n)


_STRONG_TIME = re.compile(r"(?<![\w:.\-/])\d{1,2}(?::[0-5]\d\s*(?:a\.m\.|p\.m\.|am\b|pm\b)?|\s*(?:a\.m\.|p\.m\.|am\b|pm\b))"
                          r"|\b(?:noon|midday)\b", re.I)
_RANGE = [re.compile(rf"\b(?:between|from)\s+{_t('1')}\s*(?:and|to|until|till|-|–)\s*{_t('2')}", re.I),
          re.compile(rf"(?<![\w:.\-/]){_t('1')}\s*(?:-|–)\s*{_t('2')}", re.I)]
_MARK = re.compile(r"⟦(\d+)⟧")

_NEG = r"(?:\b(?:no|not|nothing|never|none|avoid|cannot|unable|without)\b|\b\w+n't\b|\bcan not\b|\bcant\b)"
_BUSY = r"\b(?:work|working|job|shift|busy|practice|commute|appointment|unavailable)\b"

# (role, rule) in priority order; each time in a fragment is used by the first rule that reaches it.
_TIME_RULES: list[tuple[str, re.Pattern]] = [(role, re.compile(p, re.I)) for role, p in (
    ("end", rf"{_BUSY}.*\b(?:start|begin)\w*\s+(?:at\s+|around\s+)?{_t()}"),          # my shift starts at 1pm
    ("start", rf"{_BUSY}.*\b(?:end|finish|over|done)\w*\s+(?:at\s+|around\s+|by\s+)?{_t()}"),  # work ends at 10
    ("start", rf"\bnot\s+(?:free|available|around|on campus|awake|up)\s+(?:until|till|before)\s+{_t()}"),
    ("bad", rf"{_NEG}.*\b(?:until|till)\s+{_t()}"),                                # can't stay until 5 / not free until 11
    ("end", rf"{_NEG}.*\b(?:after|past|later than)\s+{_t()}"),                     # nothing after 5pm
    ("start", rf"{_NEG}.*\b(?:before|earlier than)\s+{_t()}"),                     # no classes before 10
    ("end", rf"\b(?:done|finish\w*|out|free|leave|leaving|ends?|ending|over|home|gone)\s+(?:by|before|at)\s+{_t()}"),
    ("start", rf"\b(?:start|begin)\w*\s+(?:at\s+|after\s+|from\s+|around\s+|no earlier than\s+)?{_t()}"),
    ("end", rf"\b(?:no later than|by)\s+{_t()}"),
    ("start", rf"{_BUSY}.*\b(?:before|until|till)\s+{_t()}"),                       # I work until noon
    ("end", rf"{_BUSY}.*\b(?:after|from|at)\s+{_t()}"),                            # I work after 3pm
    ("end", rf"\b(?:until|till)\s+{_t()}"),                                        # I can stay until 4
    ("start", rf"\bafter\s+{_t()}"),                                               # classes after 10am
)]

# A time limit tied to some days only, which plan_schedule cannot express.
_PARTIAL = re.compile(
    rf"\b{_ANY_DAY}\s+(?:in the\s+|\w+\s+)?(?:mornings?|afternoons?|evenings?|nights?|before|after|until|till|by)\b"
    rf"|\b(?:mornings?|afternoons?|evenings?|nights?)\s+(?:on\s+)?{_ANY_DAY}\b"
    rf"|\b(?:before|after|until|till|by)\s+[\w:. ]{{1,10}}?\s+on\s+{_ANY_DAY}\b", re.I)
# Day directions, checked in this order.
_DAY_ACCEPT = re.compile(
    r"\b(?:don't|do not|doesn't|does not|didn't|no)\s+(?:really\s+)?(?:(?:need|have|has)\s+to|mind|care)\b"
    r"|\bno need\b|\bnot a (?:big )?deal\b"
    r"|\bdoesn't matter\b|\bno other (?:way|option|choice)\b|\bnot a must\b|\bnot (?:necessary|required)\b"
    r"|\bcan't be avoided\b|\bnothing else (?:works|fits)\b|\bonly (?:way|option|choice)\b", re.I)
_DAY_NOT_OK = re.compile(r"\b(?:not|never|n't)\s+(?:\w+\s+)?(?:fine|okay|ok|alright|acceptable|good)\b|n't\s+(?:fine|okay|ok)\b",
                         re.I)
_DAY_RELAX = re.compile(r"\b(?:fine|okay|ok|alright|all right|acceptable)\b", re.I)
_DAY_AVOID = re.compile(
    rf"{_NEG}|\b(?:off|busy|work|working|job|shift|bad|problem|conflict|skip|except|impossible|unavailable|"
    r"no way|off-limits)\b|\b(?:keep|want|need|leave|have)\b.*\b(?:free|clear|open)\b|\bfree days?\b", re.I)
_DAY_ONLY = re.compile(r"\b(?:only|just|exclusively)\b", re.I)
_DAY_OK = re.compile(r"\b(?:works?|good|available|can|could|free|prefer|like|love|want|best|better)\b", re.I)

_ASK = {
    "earliest_start": "What is the earliest time a class can start for you (for example 10:00 AM)?",
    "latest_end": "By what time do your classes need to be over (for example 3:00 PM)?",
    "avoid_days": "Which days do you need to keep completely free of classes (for example Friday)?",
    "partial_day": ("Does your time limit apply to every day, or only to the days you named? I can only apply a "
                    "time limit to all days, or keep whole days free."),
    "busy_range": ("I can apply one earliest start time and one end time to every day. What is the earliest time a "
                   "class can start, and by what time do your classes need to be over?"),
    "time_role": ("Is that time the earliest your classes can start, or the time they need to be over by? Please "
                  "give it as, for example, \"no classes before 10:00 AM\" or \"done by 3:00 PM\"."),
}


class ClarificationNeeded(Exception):
    """A required constraint could not be read reliably: ask, do not plan."""

    def __init__(self, items: list[dict]):
        super().__init__("clarification needed")
        self.items = items

    def question(self) -> str:
        return clarification_question(self.items)


@dataclass
class Reading:
    preference: str
    value: str | tuple[str, ...] | None = None
    reliable: bool = False
    mentioned: bool = False
    verdict: str = "unknown"  # required | soft | conflicting | unknown (from the student's cues)
    reason: str = ""
    kind: str = ""  # why it is unreliable: vague, ampm, time_role, partial_day, busy_range, days, range
    ambiguous_hour: str | None = None
    relaxed: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        v = list(self.value) if isinstance(self.value, tuple) else self.value
        d = {"preference": self.preference, "value": v, "reliable": self.reliable, "verdict": self.verdict,
             "reason": self.reason}
        if self.relaxed:
            d["relaxed_days"] = list(self.relaxed)
        return d


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _norm_time(match: re.Match, n: str, role: str) -> tuple[str | None, str | None]:
    """(HH:MM, None) or (None, ambiguous hour as written) for one time in a match."""
    if match.group(f"noon{n}"):
        return "12:00", None
    h, m = int(match.group(f"h{n}")), int(match.group(f"m{n}") or 0)
    ap = (match.group(f"ap{n}") or "").lower().replace(".", "")
    written = f"{h}:{m:02d}" if match.group(f"m{n}") else str(h)
    if ap:
        if not 1 <= h <= 12:
            return None, None
        h = (0 if h == 12 else h) + (12 if ap == "pm" else 0)
        value = _hhmm(h, m)
    elif 13 <= h <= 23 or h == 12:
        value = _hhmm(h, m)
    elif role == "start" and 7 <= h <= 11:
        value = _hhmm(h, m)
    elif role == "start" and 1 <= h <= 6:
        value = _hhmm(h + 12, m)
    elif role == "end" and 1 <= h <= 9:
        value = _hhmm(h + 12, m)
    else:
        return None, written
    ok = ("07:00" <= value <= "18:00") if role == "start" else ("09:00" <= value <= "23:00")
    return (value, None) if ok else (None, None if ap or h >= 12 else written)


def _days_in(text: str) -> set[str]:
    days = {d for m in _DAY.finditer(text) for d, v in m.groupdict().items() if v}
    if _WEEKEND.search(text):
        days |= {"SAT", "SUN"}
    return days


@dataclass
class _Parsed:
    """What one fragment says, before aggregation."""
    times: dict = field(default_factory=lambda: {p: [] for p in TIME_PREFS})  # pref -> [(value|None, kind, hour)]
    vague: set = field(default_factory=set)  # time prefs named without a time
    avoid: set = field(default_factory=set)
    relaxed: set = field(default_factory=set)
    only: set = field(default_factory=set)  # "only Mondays": every other day is avoided
    named_days: set = field(default_factory=set)
    day_problem: str = ""  # "", "days" (no direction), "partial_day", "range"
    bare: bool = False  # nothing but day names ("Mondays" in "Mondays and Wednesdays only")

    def targets(self) -> set[str]:
        t = {p for p, v in self.times.items() if v} | self.vague
        if self.named_days or self.day_problem:
            t.add("avoid_days")
        return t


class _Extractor:
    def __init__(self, request: str):
        self.ranges: list[tuple] = []
        text = (request or "").replace("’", "'")
        for rx in _RANGE:
            text = rx.sub(self._mark, text)
        self.text = text

    def _mark(self, m: re.Match) -> str:
        self.ranges.append((_norm_time(m, "1", "start"), _norm_time(m, "2", "end")))
        return f" ⟦{len(self.ranges) - 1}⟧ "

    @lru_cache(maxsize=None)  # noqa: B019 - one extractor per request
    def parse(self, fragment: str) -> _Parsed:
        p = _Parsed()
        text = _COURSE.sub(" ", fragment)
        partial = bool(_PARTIAL.search(text))
        busy_or_neg = re.search(_BUSY, text, re.I) or re.search(_NEG, text, re.I)

        for m in _MARK.finditer(text):  # time ranges
            (a, amb_a), (b, amb_b) = self.ranges[int(m.group(1))]
            for pref, value, amb in (("earliest_start", a, amb_a), ("latest_end", b, amb_b)):
                if partial:
                    p.times[pref].append((None, "partial_day", None))
                elif busy_or_neg:
                    p.times[pref].append((None, "busy_range", None))
                else:
                    p.times[pref].append((value, "ampm" if amb else "", amb) if value else (None, "ampm", amb))
        text = _MARK.sub(" ", text)

        used: list[tuple[int, int]] = []
        for role, rule in _TIME_RULES:
            for m in rule.finditer(text):
                span = m.span("h") if m.group("h") else m.span("noon")
                if any(a <= span[0] < b for a, b in used):
                    continue
                used.append(span)
                if role == "bad":
                    for pref in TIME_PREFS:
                        p.times[pref].append((None, "time_role", None))
                    continue
                pref = "earliest_start" if role == "start" else "latest_end"
                value, amb = _norm_time(m, "", role)
                if partial:
                    p.times[pref].append((None, "partial_day", None))
                elif value:
                    p.times[pref].append((value, "", None))
                else:
                    p.times[pref].append((None, "ampm" if amb else "time_role", amb))
        for m in _STRONG_TIME.finditer(text):  # a clear time no rule could place
            if not any(a <= m.start() < b for a, b in used):
                for pref in TIME_PREFS:
                    p.times[pref].append((None, "partial_day" if partial else "time_role", None))
        if not any(p.times.values()):
            vague = _targets(text) & set(TIME_PREFS)  # "mornings", "late", "start", ...
            if partial:
                for pref in vague:
                    p.times[pref].append((None, "partial_day", None))
            else:
                p.vague = vague

        days = _days_in(text)
        if days:
            p.named_days = days
            p.bare = not re.sub(rf"{_DAY.pattern}|{_WEEKEND.pattern}|\b(?:on|the|or|and|every|classes?)\b|[\W_]+",
                                "", text, flags=re.I)
            if _DAY_RANGE.search(text):
                p.day_problem = "range"
            elif partial:
                p.day_problem = "partial_day"
            elif _DAY_ACCEPT.search(text):
                p.relaxed |= days
            elif _DAY_NOT_OK.search(text):
                p.avoid |= days
            elif _DAY_RELAX.search(text):
                p.relaxed |= days
            elif _DAY_AVOID.search(text):
                p.avoid |= days
            elif _DAY_ONLY.search(text):
                p.only |= days
            elif _DAY_OK.search(text):
                p.relaxed |= days
            elif not p.bare:
                p.day_problem = "days"
        return p

    def targets(self, fragment: str) -> set[str]:
        return self.parse(fragment).targets()


def _verdict(optional: set, mandatory: set) -> str:
    if optional and not mandatory:
        return "soft"
    if mandatory and not optional:
        return "required"
    return "conflicting" if mandatory else "unknown"


_REASONS = {
    "vague": "no specific time is stated",
    "ampm": "the time could be AM or PM",
    "time_role": "a time is not clearly a start or an end limit",
    "partial_day": "the limit applies to some days only",
    "busy_range": "a busy time range is stated, not a start or end limit",
    "days": "it is not clear which days to keep free",
    "range": "a range of days is stated",
}


def extract(request: str) -> dict[str, Reading]:
    """Per preference: the value the student stated, its strength, and whether it is reliable."""
    ex = _Extractor(request)
    frags = fragments(ex.text, linker=ex.targets)
    cues = {p: (set(), set()) for p in PREFS}
    times: dict[str, list] = {p: [] for p in TIME_PREFS}
    vague: dict[str, bool] = {p: False for p in TIME_PREFS}
    avoid: set[str] = set()
    relaxed: set[str] = set()
    only: set[str] = set()
    day_problem = ""
    mentioned: set[str] = set()
    named = [f for f in frags if not f["cue_only"]]
    for i, f in enumerate(frags):
        for pref in f["targets"]:
            mentioned.add(pref)
            cues[pref][0].update(f["optional"])
            cues[pref][1].update(f["mandatory"])
        if f["cue_only"]:
            continue
        parsed = ex.parse(f["text"])
        for pref in TIME_PREFS:
            times[pref] += parsed.times[pref]
            vague[pref] |= pref in parsed.vague
        if parsed.bare and not (parsed.avoid or parsed.relaxed or parsed.only or parsed.day_problem):
            # bare day names take the direction of the nearest day fragment of the same
            # sentence, next one first: "Mondays and Wednesdays only", "avoid Fridays and Mondays"
            j = named.index(f)
            same = [g for g in named[j + 1:] + named[:j][::-1] if g["sentence"] == f["sentence"]]
            src = next((ex.parse(g["text"]) for g in same
                        if (lambda q: q.avoid or q.relaxed or q.only or q.day_problem)(ex.parse(g["text"]))), None)
            if src is None or src.day_problem:
                day_problem = day_problem or "days"
            elif src.only:
                only |= parsed.named_days
            elif src.avoid:
                avoid |= parsed.named_days
            else:
                relaxed |= parsed.named_days
        avoid |= parsed.avoid
        relaxed |= parsed.relaxed
        only |= parsed.only
        day_problem = day_problem or parsed.day_problem
    if only:
        avoid |= set(WEEK) - only - relaxed

    out: dict[str, Reading] = {}
    for pref in TIME_PREFS:
        r = Reading(pref, mentioned=pref in mentioned, verdict=_verdict(*cues[pref]))
        values = {v for v, _, _ in times[pref] if v}
        problems = [(kind, hour) for v, kind, hour in times[pref] if not v]
        if not r.mentioned:
            r.reason = "not mentioned"
        elif problems:
            r.kind = problems[0][0]
            r.ambiguous_hour = next((h for k, h in problems if h), None)
        elif not values:
            r.kind = "vague"
        else:
            # several limits for one preference ("my shift starts at 1pm, so done by 12:30"):
            # the strictest satisfies all of them
            r.value = max(values) if pref == "earliest_start" else min(values)
            r.reliable = True
            r.reason = ("read from the student's words" if len(values) == 1
                        else "several limits are stated; the strictest is used")
        r.reason = r.reason or _REASONS[r.kind]
        out[pref] = r

    r = Reading("avoid_days", mentioned="avoid_days" in mentioned, verdict=_verdict(*cues["avoid_days"]))
    if not r.mentioned:
        r.reason = "not mentioned"
    elif day_problem:
        r.kind, r.reason = day_problem, _REASONS[day_problem]
    elif avoid:
        # a day both avoided and accepted was relaxed by the student ("Fridays are fine if I have to")
        r.value, r.reliable, r.reason = tuple(d for d in WEEK if d in avoid), True, "read from the student's words"
        r.relaxed = tuple(d for d in WEEK if d in avoid & relaxed)
    else:
        r.value, r.reliable, r.reason = (), True, "only acceptable days are named"
    out["avoid_days"] = r
    return out


def mentioned(request: str) -> set[str]:
    """Preferences the student's words talk about, including wording that
    preference_language.unmentioned() does not link ("between 10 and 3")."""
    return {p for p, r in extract(request).items() if r.mentioned}


@dataclass
class Resolution:
    earliest_start: str | None
    latest_end: str | None
    avoid_days: list[str]
    required: list[str]
    changes: list[dict]
    clarify: list[dict]
    readings: dict


def _clarify_item(r: Reading) -> dict:
    return {"preference": r.preference, "reason": r.reason, "kind": r.kind, "ambiguous_hour": r.ambiguous_hour}


def resolve(request: str, earliest_start: str | None, latest_end: str | None, avoid_days: list[str] | None,
            required: list[str]) -> Resolution:
    """Apply the student's own clearly stated constraints over the model's arguments.

    Called after unmentioned()/reconcile(), so `required` is the reconciled list."""
    readings = extract(request)
    model = {"earliest_start": earliest_start or None, "latest_end": latest_end or None,
             "avoid_days": tuple(d for d in WEEK if d in set(avoid_days or []))}
    applied = dict(model)
    req = {r for r in required if r in PREFS}
    changes: list[dict] = []
    clarify: list[dict] = []
    show = (lambda v: list(v) if isinstance(v, tuple) else v)
    for pref in PREFS:
        r = readings[pref]
        if not r.mentioned:
            continue
        if r.verdict == "required" and not r.reliable:
            clarify.append(_clarify_item(r))
            continue
        if not r.reliable or (pref == "avoid_days" and not r.value):
            continue
        if r.value != model[pref]:
            changes.append({"preference": pref, "model_value": show(model[pref]), "applied": show(r.value),
                            "reason": ("the model left out a constraint the student stated" if not model[pref]
                                       else "the model's value differs from the student's words")})
            applied[pref] = r.value
        if r.verdict == "required" and pref not in req:
            req.add(pref)
            changes.append({"preference": pref, "model_value": "soft", "applied": "required",
                            "reason": "the student's words make it mandatory"})
        elif r.verdict == "unknown" and not model[pref] and pref not in req:
            # nothing softens it and the model gave no reading: treat it as a limit,
            # so no option breaks it ("No Friday classes.")
            req.add(pref)
            changes.append({"preference": pref, "model_value": None, "applied": "required",
                            "reason": "stated without softening words; the model left it out"})
    return Resolution(applied["earliest_start"], applied["latest_end"], list(applied["avoid_days"]),
                      sorted(req), changes, clarify, {p: r.to_dict() for p, r in readings.items() if r.mentioned})


def clarifications(request: str) -> list[dict]:
    """Required constraints that cannot be read reliably (what resolve() would ask about)."""
    return [_clarify_item(r) for r in extract(request).values()
            if r.mentioned and r.verdict == "required" and not r.reliable]


def system_arguments(request: str) -> dict | None:
    """plan_schedule preference arguments read only from the student's words, for
    the evidence-check recovery. None if any stated constraint is unreliable or
    both required and relaxed (then the conversation has to settle it)."""
    args: dict = {}
    required = []
    for pref, r in extract(request).items():
        if not r.mentioned:
            continue
        if not r.reliable or r.verdict == "conflicting":
            return None
        if pref == "avoid_days" and not r.value:
            continue
        args[pref] = list(r.value) if pref == "avoid_days" else r.value
        if r.verdict in ("required", "unknown"):  # as in resolve(): unsoftened limits are mandatory
            required.append(pref)
    if required:
        args["required_preferences"] = required
    return args


def clarification_question(items: list[dict]) -> str:
    """A fixed question. Nothing from the student's message is repeated except an hour number."""
    lines = ["Before I build your schedule, I need one detail so I don't suggest sections that break something "
             "you said you can't do:"]
    asked: set[str] = set()
    for item in items:
        hour = item.get("ambiguous_hour")
        if item.get("kind") == "ampm" and hour and re.fullmatch(r"\d{1,2}(:\d{2})?", hour):
            what = "the earliest start" if item["preference"] == "earliest_start" else "the time to be done by"
            line = f"When you said {hour}, did you mean {hour} AM or {hour} PM (as {what})?"
        elif item.get("kind") in ("partial_day", "time_role", "busy_range"):
            line = _ASK[item["kind"]]
        else:
            line = _ASK[item["preference"]]
        if line not in asked:
            asked.add(line)
            lines.append("- " + line)
    return "\n".join(lines)


