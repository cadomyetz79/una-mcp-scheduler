"""Deterministic reading of HOW STRONGLY a student states a preference.

The model decides which preferences exist (earliest_start, latest_end,
avoid_days) and whether each is mandatory (required_preferences). The live
qwen3:8b run on 2026-10-19 marked "I'd prefer no classes before 10am if
possible" as mandatory, which wrongly removed a valid course. This module is a
second, rule-based opinion taken from the student's own words.

How it works:
1. Split the request into clauses (sentences, then ", but", ", and", "; ").
2. A clause is about TIME if it mentions a clock time or words like
   before/after/morning/done by; about DAYS if it names a weekday.
3. Collect strength cues in those clauses:
     optional  - prefer, ideally, if possible, rather, would like, hopefully ...
     mandatory - must, can't, cannot, have to, need to, required, at all ...
4. Verdict per preference group: "soft" if only optional cues, "required" if
   only mandatory cues, otherwise "unknown" (no cue, or both kinds).

Only clear verdicts are used, and only to correct the model's mandatory/soft
flag for a preference the model itself stated. "unknown" never changes
anything, so ambiguous wording stays with the model's reading.

Known limits (WORKING ASSUMPTION): English only; keyword based, so unusual
phrasing or negated cues ("I don't have to ...") can be misread, which is
why mixed signals give "unknown".
"""

from __future__ import annotations

import re

OPTIONAL_CUES = (
    "prefer", "preferably", "ideally", "if possible", "if you can", "if it's possible",
    "rather", "would like", "i'd like", "would be nice", "would be great", "hopefully",
    "if that works", "nice to have", "try to", "wish",
)
MANDATORY_CUES = (
    "must", "can't", "cant", "cannot", "can not", "unable", "not able", "have to",
    "has to", "need to", "needs to", "required", "requirement", "no way", "at all",
    "never", "impossible", "only available", "absolutely",
)

_TIME = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.)|\b(before|after|until|by)\s+\d{1,2}\b"
    r"|\bmornings?\b|\bafternoons?\b|\bevenings?\b|\bnoon\b|\bearly\b|\blate\b"
    r"|\bdone by\b|\bend by\b|\bfinish(ed)? by\b|\bstart(s|ing)?\b",
    re.IGNORECASE,
)
_DAYS = re.compile(
    r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day)?s?\b|\bweekends?\b",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[.!?;\n]+|,\s*(?:but|and|so|while)\b|\bbut\b", re.IGNORECASE)

GROUPS = {"earliest_start": "time", "latest_end": "time", "avoid_days": "days"}


def _cues(text: str, cues: tuple[str, ...]) -> list[str]:
    low = text.lower().replace("’", "'")
    return [c for c in cues if re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", low)]


def classify(request: str) -> dict[str, dict]:
    """Return {"time": {...}, "days": {...}} with verdict and the cues found."""
    clauses = [c.strip() for c in _SPLIT.split(request or "") if c and c.strip()]
    out = {}
    for group, pattern in (("time", _TIME), ("days", _DAYS)):
        relevant = [c for c in clauses if pattern.search(c)]
        optional = sorted({q for c in relevant for q in _cues(c, OPTIONAL_CUES)})
        mandatory = sorted({q for c in relevant for q in _cues(c, MANDATORY_CUES)})
        if optional and not mandatory:
            verdict = "soft"
        elif mandatory and not optional:
            verdict = "required"
        else:
            verdict = "unknown"
        out[group] = {"verdict": verdict, "optional_cues": optional,
                      "mandatory_cues": mandatory, "clauses": relevant}
    return out


def reconcile(request: str, stated: list[str], required: list[str]) -> tuple[list[str], list[dict]]:
    """Correct the model's required list where the student's words are clear.

    stated   - preferences the model actually set (non-empty values)
    required - the model's required_preferences
    Returns (required list to apply, list of corrections made).
    """
    reading = classify(request)
    applied = [r for r in required if r in GROUPS]
    corrections = []
    for pref in stated:
        info = reading[GROUPS[pref]]
        model_says = "required" if pref in applied else "soft"
        if info["verdict"] in ("soft", "required") and info["verdict"] != model_says:
            if info["verdict"] == "soft":
                applied.remove(pref)
            else:
                applied.append(pref)
            corrections.append({
                "preference": pref,
                "model_said": model_says,
                "applied": info["verdict"],
                "evidence": info["optional_cues"] if info["verdict"] == "soft" else info["mandatory_cues"],
            })
    return sorted(set(applied)), corrections
