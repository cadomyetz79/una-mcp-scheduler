# Held-out evaluation data

Synthetic data for the HELD-OUT evaluation set only (`../cases.json`). It is
the team's `data/*.json` (unchanged) plus new students, courses and sections
so the held-out requests can reach scenarios the development data cannot:

- S20001 Riley: credit limit 9 (CREDIT_LIMIT_EXCEEDED reachable)
- S20002 Morgan: has completed CIS376 (ALREADY_COMPLETED reachable)
- S20003 Casey: inactive but has the prerequisites (STUDENT_INACTIVE reachable)
- S20004 Drew: new student with no course history
- S20005 Avery: CIS376 in progress (in_progress does not satisfy a prerequisite)
- CIS345 / CIS346: corequisites of each other
- CIS480: in the catalog, no sections in 2027SP
- SEC5501: a section for CIS399, which is NOT in courses.json (incomplete data)
- SEC5001 and SEC5301 overlap (TUE/THU 09:30-10:45); SEC5102 is full

The development data in `data/` is not modified.
