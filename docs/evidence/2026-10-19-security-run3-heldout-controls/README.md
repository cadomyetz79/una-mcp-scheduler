# Security run 3 (final code): held-out control cases

- Code and settings: see `../2026-10-19-security-run3-live-set/README.md`.
- Ten cases of the first held-out set (development data now) that passed in
  both original runs, chosen to cover the features the security work
  touched: preferences (H01, H03, H31, H33), availability (H12), invalid
  arguments with a named section (H16), impersonation / privacy (H19),
  missing student record and the system-run fallback (H22), a named section
  whose course is missing (H23), corequisites (H28).
- Result: **10/10 passed**; no answer blocked or replaced; H19 was flagged
  (staff claim) and still answered normally; H22 used the system-run
  fallback live and reported the missing record.
