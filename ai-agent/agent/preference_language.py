"""Deterministic reading of HOW STRONGLY a student states each preference.

The model decides which preferences exist (earliest_start, latest_end,
avoid_days) and whether each is mandatory (required_preferences). The live
qwen3:8b baseline on 2026-10-19 got this wrong in both directions ("if
possible" treated as mandatory, "can't" treated as optional). This module is
a second, rule-based opinion taken only from the student's own words, and it
is applied PER PREFERENCE, never as one global switch for the request.

How a request is read:
1. Split into sentences, then into fragments at commas and at "and", "but",
   "so", "while", "also".
2. Each fragment is linked to the preference(s) it talks about:
     earliest_start  "start", "morning", "early", "before 10", "after 10am"
     latest_end      "done/finish/end/out/free by", "until", "afternoon",
                     "evening", "late", "after 3pm", "by 3"
     avoid_days      weekday names, "weekends"
   A fragment about a finishing time ("done before 3pm") is latest_end, not
   earliest_start.
3. Strength cues in the fragment:
     optional   prefer, ideally, if possible, rather, would like, hopefully,
                flexible, don't mind, ...
     mandatory  must, can't, cannot, have to, need to, required, at all, ...
   A mandatory cue that is negated in front ("don't have to", "no need to",
   "not required") counts as optional.
4. A fragment with cues but no preference ("if possible," / ", I really
   can't") lends its cues to the nearest fragment of the same sentence that
   names a preference (previous one first); if its sentence names none, to
   the preferences of the latest earlier sentence that named one ("I can't
   do Fridays. If there's no other way, that's fine."). Fragments about
   courses ("I need CIS376") are ignored. A mandatory word inside a
   relaxation ("have to" in "if I have to") is not a separate cue.
5. Verdict per preference: "soft" if only optional cues, "required" if only
   mandatory cues, "conflicting" if both kinds, "unknown" if none.

Only clear verdicts are used, and only to correct the mandatory/soft flag of
a preference the model itself stated. "unknown" and "conflicting" never
change anything: the model's reading stands, and a conflict is reported
(deferrals()) so it is visible in the trace.

Relaxations (added 2026-10-19 after held-out case H32, which is now
development data): "I must avoid Wednesdays. Actually, Wednesdays are fine
if there's no other way." The second sentence relaxes the first, but
"fine" and "no other way" were not cues, so the check read the preference as
mandatory and overrode the model's correct "soft". Relaxation phrases are now
optional cues ("fine", "okay", "acceptable" only in a fragment that names the
preference itself, so "OK, I can't do Fridays" is not a relaxation; "if
there's no other way", "if I have to", "as a last resort" also as a separate
fragment), and a negated one ("Fridays are not okay") is mandatory. A
preference that is both required and relaxed is "conflicting": the check
does not override the model without clear evidence.

Limits (WORKING ASSUMPTION): English only; keyword based; written and tested
by the project team, not validated on real student wording yet.
"""

from __future__ import annotations

import re

PREFS = ("earliest_start", "latest_end", "avoid_days")

OPTIONAL_CUES = (
    "prefer", "preferably", "preferred", "ideally", "if possible", "if you can", "if it's possible",
    "rather", "would like", "i'd like", "would be nice", "would be great", "hopefully",
    "if that works", "nice to have", "try to", "flexible", "don't mind", "do not mind",
    "doesn't matter", "not a big deal", "if needed", "if necessary", "not necessary",
    # conditional relaxations: "X is fine if there's no other way"
    "no other way", "no other option", "no other choice", "if i have to", "if i must", "if we have to",
    "last resort", "can live with", "if nothing else works", "if it can't be avoided",
)
# Relaxation words that count only inside a fragment naming the preference
# itself ("Wednesdays are fine"), never lent from a cue-only fragment ("OK,").
RELAX_CUES = ("fine", "okay", "ok", "alright", "all right", "acceptable")
_NEGATED_RELAX = re.compile(r"(not|n't|never|no longer)\s+(\w+\s+)?$")
MANDATORY_CUES = (
    "must", "can't", "cant", "cannot", "can not", "unable", "not able", "have to", "has to",
    "need to", "needs to", "required", "requirement", "no way", "at all", "never",
    "impossible", "only available", "absolutely", "mandatory",
)
# A mandatory cue preceded by one of these is a negated obligation -> optional.
_NEGATED = re.compile(r"(don't|do not|doesn't|does not|didn't|not|no)\s+(really\s+)?$")

_HOUR = r"\d{1,2}(:\d{2})?"
_AM = r"\s*(am|a\.m\.)"
_PM = r"\s*(pm|p\.m\.)"
_END_WORDS = re.compile(r"\b(done|finish(ed|es)?|end(s|ed)?|out|free|leave)\b", re.I)
_EARLIEST = re.compile(
    rf"\bstart(s|ing)?\b|\bmornings?\b|\bearly\b|\bbefore\s+{_HOUR}|\bafter\s+{_HOUR}{_AM}"
    rf"|\bafter\s+{_HOUR}(?!\s*(pm|p\.m\.))\b", re.I)
_LATEST = re.compile(
    rf"\b(done|finish(ed)?|end|out|free)\s+(by|before)\b|\buntil\b|\bafternoons?\b|\bevenings?\b"
    rf"|\bnights?\b|\blate\b|\bafter\s+{_HOUR}{_PM}|\bby\s+{_HOUR}", re.I)
# Full weekday names need their own stems: "wed"+"day" never matched "wednesday".
_DAYS = re.compile(r"\b(mon|tues?|wed(nes)?|thu(rs?)?|fri|sat(ur)?|sun)(day)?s?\b|\bweekends?\b", re.I)
_COURSE = re.compile(r"\b[A-Z]{2,4}\s?\d{3}\b")
_SENTENCES = re.compile(r"[.!?;\n]+")
_FRAGMENTS = re.compile(r",|\b(?:and|but|so|while|also)\b", re.I)


def _targets(fragment: str) -> set[str]:
    found = set()
    if _DAYS.search(fragment):
        found.add("avoid_days")
    is_end = bool(_END_WORDS.search(fragment))
    if _LATEST.search(fragment) or (is_end and re.search(_HOUR, fragment)):
        found.add("latest_end")
    if _EARLIEST.search(fragment) and not is_end:
        found.add("earliest_start")
    return found


def _cues(fragment: str) -> tuple[set[str], set[str]]:
    low = fragment.lower().replace("’", "'")
    optional, mandatory = set(), set()
    spans: list[tuple[int, int]] = []
    for cue in OPTIONAL_CUES:
        for m in re.finditer(r"(?<![a-z'])" + re.escape(cue) + r"(?![a-z])", low):
            optional.add(cue)
            spans.append(m.span())
    for cue in MANDATORY_CUES:
        for m in re.finditer(r"(?<![a-z'])" + re.escape(cue) + r"(?![a-z])", low):
            if any(a <= m.start() and m.end() <= b for a, b in spans):
                continue  # "have to" inside the relaxation "if I have to"
            if cue in ("must", "have to", "has to", "need to", "needs to", "required", "mandatory") \
                    and _NEGATED.search(low[: m.start()]):
                optional.add("not " + cue)
            else:
                mandatory.add(cue)
    for cue in RELAX_CUES:
        for m in re.finditer(r"(?<![a-z'])" + re.escape(cue) + r"(?![a-z])", low):
            if _NEGATED_RELAX.search(low[: m.start()]):
                mandatory.add("not " + cue)  # "Fridays are not okay"
            else:
                optional.add(cue)
    return optional, mandatory


def classify(request: str) -> dict[str, dict]:
    """Return, per preference, the verdict and the cues/fragments behind it."""
    found = {p: {"optional": set(), "mandatory": set(), "fragments": []} for p in PREFS}
    previous_targets: set[str] = set()  # preferences named by the latest earlier sentence
    for sentence in _SENTENCES.split(request or ""):
        frags = [f.strip() for f in _FRAGMENTS.split(sentence) if f and f.strip()]
        info = [(f, _targets(f), *_cues(f)) for f in frags]
        for i, (frag, targets, opt, man) in enumerate(info):
            if not targets:
                if _COURSE.search(frag) or not (opt or man):
                    continue
                # cue-only fragment: lend cues to the nearest fragment naming a preference
                # in the same sentence, else to the previous sentence's preferences
                # ("I can't do Fridays. If there's no other way, that's fine.")
                neighbours = [j for j in range(i - 1, -1, -1) if info[j][1]] or \
                             [j for j in range(i + 1, len(info)) if info[j][1]]
                if neighbours:
                    targets = info[neighbours[0]][1]
                elif previous_targets:
                    targets = previous_targets
                else:
                    continue
                # bare "fine"/"okay" only relax the preference named in their own fragment
                opt = {c for c in opt if c not in RELAX_CUES}
                man = {c for c in man if c.removeprefix("not ") not in RELAX_CUES}
                if not (opt or man):
                    continue
            for p in targets:
                found[p]["optional"] |= opt
                found[p]["mandatory"] |= man
                found[p]["fragments"].append(frag)
        named = set().union(*(t for _, t, _, _ in info)) if info else set()
        if named:
            previous_targets = named

    out = {}
    for p, f in found.items():
        if f["optional"] and not f["mandatory"]:
            verdict = "soft"
        elif f["mandatory"] and not f["optional"]:
            verdict = "required"
        elif f["mandatory"] and f["optional"]:
            verdict = "conflicting"
        else:
            verdict = "unknown"
        out[p] = {"verdict": verdict, "optional_cues": sorted(f["optional"]),
                  "mandatory_cues": sorted(f["mandatory"]), "fragments": f["fragments"]}
    return out


def reconcile(request: str, stated: list[str], required: list[str]) -> tuple[list[str], list[dict]]:
    """Correct the model's required list where the student's words are clear.

    stated   - preferences the model actually set (non-empty values)
    required - the model's required_preferences
    Returns (required list to apply, list of corrections made).
    """
    reading = classify(request)
    applied = {r for r in required if r in PREFS}
    corrections = []
    for pref in stated:
        info = reading[pref]
        model_says = "required" if pref in applied else "soft"
        if info["verdict"] in ("soft", "required") and info["verdict"] != model_says:
            if info["verdict"] == "soft":
                applied.discard(pref)
            else:
                applied.add(pref)
            corrections.append({
                "preference": pref,
                "model_said": model_says,
                "applied": info["verdict"],
                "evidence": info["optional_cues"] if info["verdict"] == "soft" else info["mandatory_cues"],
            })
    return sorted(applied), corrections


_TOPIC = {"earliest_start": "start times", "latest_end": "end times", "avoid_days": "days"}


def unmentioned(request: str, stated: list[str]) -> list[dict]:
    """Stated preferences the student's message never talks about.

    Live runs on 2026-10-19 (security live set SL05, SL10, development data)
    showed qwen3:8b adding earliest_start 08:00 / latest_end 17:00 (and once a
    mandatory "avoid Fridays") to requests that mention no time or day at all,
    which removed valid schedules. A time or day wish whose subject never
    appears in the request (no fragment about start times, end times or days)
    has no basis in the student's words and is not applied. Limit: implicit
    wording the patterns do not know (e.g. "I have practice after lunch") is
    treated as not mentioned."""
    reading = classify(request)
    return [{"preference": p, "reason": f"the student's message does not mention {_TOPIC[p]}"}
            for p in stated if not reading[p]["fragments"]]


def deferrals(request: str, stated: list[str], required: list[str]) -> list[dict]:
    """Stated preferences whose wording both requires and relaxes them: the
    model's reading is kept, and this records why the check did not act."""
    reading = classify(request)
    applied = {r for r in required if r in PREFS}
    return [
        {"preference": p, "model_said": "required" if p in applied else "soft", "applied": "model's reading",
         "reason": "the student's words both require and relax this preference",
         "optional_cues": reading[p]["optional_cues"], "mandatory_cues": reading[p]["mandatory_cues"]}
        for p in stated if reading[p]["verdict"] == "conflicting"
    ]
