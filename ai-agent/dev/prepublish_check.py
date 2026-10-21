#!/usr/bin/env python3
"""Pre-publication privacy check for commits, pull requests and comments.

Run it before pushing commits or posting a pull request description or a
comment. It looks for:

- links to Claude sessions or conversations, and session trailers in commit
  messages (private links must never be published);
- promotional "generated with" footers and AI co-author trailers (not added
  automatically; allow the trailer with --allow-ai-coauthor only when a
  course or project policy requires it);
- credentials: GitHub, Anthropic/OpenAI, AWS, Google and Slack keys or
  tokens, private keys, passwords in URLs, quoted secret assignments.

Findings are printed by category and location only. The matched text is
never printed, so the check itself cannot leak what it finds.

Usage (from anywhere in the repository):

    python ai-agent/dev/prepublish_check.py --range origin/main..HEAD
    python ai-agent/dev/prepublish_check.py --range <base>..HEAD --text-file pr-body.md
    python ai-agent/dev/prepublish_check.py --message-file .git/COMMIT_EDITMSG
    python ai-agent/dev/prepublish_check.py --install-hook

--range scans the messages of the commits in the range and the lines the
range adds. A commit that is already published and cannot be changed
without rewriting history can be acknowledged with --allow-commit <sha>:
its message findings are still listed, but they do not fail the check.

--install-hook writes a local commit-msg hook (in .git/hooks, not committed)
that runs --message-file on every new commit message and rejects it on a
finding. Exit status: 0 no unacknowledged findings, 1 findings, 2 usage error.

Limits: pattern based. It cannot recognise every kind of secret or personal
data, so it supports a review; it does not replace one.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Patterns are written so that this file does not match itself.
CHECKS: list[tuple[str, re.Pattern]] = [
    ("claude_session_trailer", re.compile(r"Claude[-]Session:[ \t]*\S+", re.I)),
    ("claude_session_link", re.compile(r"claude\.ai/code/session_[A-Za-z0-9]+", re.I)),
    ("claude_conversation_link", re.compile(r"claude\.ai/(?:chat|share|project)/[0-9a-f][0-9a-f-]{7,}", re.I)),
    ("promotional_footer", re.compile(r"Generated with \[?Claude Code", re.I)),
    ("ai_coauthor_trailer", re.compile(r"^[ \t]*Co-Authored-By:[ \t]*Claude\b", re.I | re.M)),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("api_key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("credential_in_url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]+:[^\s/@'\"]+@([^\s/:'\"]+)", re.I)),
    ("secret_assignment", re.compile(
        r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token)\b\s*[:=]\s*"
        r"['\"]([^'\"\s]{8,})['\"]", re.I)),
]
# Obviously fake values used in tests and documentation.
_PLACEHOLDER = re.compile(r"example|\.invalid\b|not-a-real|placeholder|changeme|dummy|localhost|127\.0\.0\.1|<[^>]+>",
                          re.I)
_PLACEHOLDER_CHECKS = {"credential_in_url", "secret_assignment"}


@dataclass
class Finding:
    category: str
    location: str
    digest: str  # sha256 prefix of the matched text, to tell findings apart without showing them
    acknowledged: bool = False

    def line(self) -> str:
        status = "ACKNOWLEDGED" if self.acknowledged else "FAIL"
        return f"{status:12} {self.category:26} {self.location}  (match sha256 {self.digest})"


def scan_text(text: str, location: str, allow_ai_coauthor: bool = False) -> list[Finding]:
    """Findings in one text. location may contain {line}, filled with the line number."""
    found = []
    for category, pattern in CHECKS:
        if category == "ai_coauthor_trailer" and allow_ai_coauthor:
            continue
        for m in pattern.finditer(text or ""):
            if category in _PLACEHOLDER_CHECKS and _PLACEHOLDER.search(m.group(0)):
                continue
            line = text.count("\n", 0, m.start()) + 1
            found.append(Finding(category, location.format(line=line),
                                 hashlib.sha256(m.group(0).encode()).hexdigest()[:10]))
    return found


def _git(*args: str, cwd: Path | None = None) -> str:
    # git writes commit messages and diffs as UTF-8; the platform default (cp1252 on
    # Windows) would garble or reject them
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def scan_range(rev_range: str, allow_commits: set[str], allow_ai_coauthor: bool = False,
               cwd: Path | None = None) -> tuple[list[Finding], int, int]:
    """Commit messages and added lines of a range like base..HEAD."""
    findings: list[Finding] = []
    commits = [c for c in _git("rev-list", rev_range, cwd=cwd).split() if c]
    allowed = {_git("rev-parse", a, cwd=cwd).strip() for a in allow_commits}
    for sha in commits:
        message = _git("log", "-1", "--format=%B", sha, cwd=cwd)
        for f in scan_text(message, f"commit {sha[:7]} message line {{line}}", allow_ai_coauthor):
            f.acknowledged = sha in allowed
            findings.append(f)
    base, _, head = rev_range.partition("..")
    diff = _git("diff", "--unified=0", "--no-color", "--no-ext-diff", base, head or "HEAD", cwd=cwd)
    path, number, added = "?", 0, 0
    for row in diff.splitlines():
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else row[4:]
        elif row.startswith("@@"):
            m = re.search(r"\+(\d+)", row)
            number = int(m.group(1)) if m else 0
        elif row.startswith("+"):
            added += 1
            findings += scan_text(row[1:], f"{path}:{number}", allow_ai_coauthor)
            number += 1
    return findings, len(commits), added


def hook_text() -> str:
    """The commit-msg hook: a POSIX shell script. Git for Windows runs hooks with its
    own sh, so the paths use forward slashes and the file keeps LF line endings."""
    python = Path(sys.executable).as_posix()
    script = Path(__file__).resolve().as_posix()
    return ("#!/bin/sh\n# installed by prepublish_check.py --install-hook (local only, not committed)\n"
            f'exec "{python}" "{script}" --message-file "$1"\n')


def install_hook(repo: Path, force: bool = False) -> Path:
    hook = repo / ".git" / "hooks" / "commit-msg"
    body = hook_text()
    if hook.exists() and hook.read_text(encoding="utf-8") != body and not force:
        raise SystemExit(f"{hook} exists; use --force to replace it")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(body, encoding="utf-8", newline="\n")  # no CRLF on Windows: sh would break
    # Executable bits matter on Linux and macOS; on Windows Git runs the hook without them.
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--range", dest="rev_range", help="commits to check, e.g. origin/main..HEAD")
    p.add_argument("--text-file", action="append", default=[], help="a PR description or comment to check")
    p.add_argument("--message-file", help="a commit message file (commit-msg hook); # lines are ignored")
    p.add_argument("--allow-commit", action="append", default=[],
                   help="an already-published commit whose message findings are acknowledged")
    p.add_argument("--allow-ai-coauthor", action="store_true",
                   help="allow AI co-author trailers (only where a policy requires them)")
    p.add_argument("--install-hook", action="store_true", help="install the local commit-msg hook")
    p.add_argument("--force", action="store_true", help="with --install-hook: replace an existing hook")
    p.add_argument("--repo", default=".", help="repository directory (default: current)")
    a = p.parse_args(argv)
    try:
        repo = Path(_git("rev-parse", "--show-toplevel", cwd=Path(a.repo)).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        repo = Path(a.repo)
    if a.install_hook:
        print(f"installed {install_hook(repo, a.force)}")
        return 0
    if not (a.rev_range or a.text_file or a.message_file):
        p.print_usage(sys.stderr)
        print("give --range, --text-file and/or --message-file", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    summary = []
    if a.rev_range:
        try:
            got, commits, added = scan_range(a.rev_range, set(a.allow_commit), a.allow_ai_coauthor, cwd=repo)
        except subprocess.CalledProcessError as e:
            print(f"git failed: {' '.join(e.cmd)}", file=sys.stderr)
            return 2
        findings += got
        summary.append(f"{commits} commit message(s) and {added} added line(s) in {a.rev_range}")
    for name in a.text_file:
        findings += scan_text(Path(name).read_text(encoding="utf-8"), f"{name}:{{line}}", a.allow_ai_coauthor)
        summary.append(name)
    if a.message_file:
        text = "\n".join(row for row in Path(a.message_file).read_text(encoding="utf-8").splitlines()
                         if not row.startswith("#"))
        findings += scan_text(text, "commit message line {line}", a.allow_ai_coauthor)
        summary.append("the commit message")

    for f in findings:
        print(f.line())
    failing = [f for f in findings if not f.acknowledged]
    checked = "; ".join(summary)
    if failing:
        print(f"prepublish check: {len(failing)} finding(s) to fix in {checked}", file=sys.stderr)
        return 1
    acknowledged = len(findings) - len(failing)
    print(f"prepublish check: OK ({checked})" + (f"; {acknowledged} acknowledged" if acknowledged else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
