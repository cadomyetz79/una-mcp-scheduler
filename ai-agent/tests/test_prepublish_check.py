"""Tests for dev/prepublish_check.py (the pre-publication privacy check).

Sensitive-looking samples are assembled at run time, so this file itself
contains no session link, footer, trailer or key that the check would flag.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dev import prepublish_check as check

ROOT = Path(__file__).resolve().parents[2]

SESSION_LINK = "https://claude" + ".ai/code/" + "session_" + "AbC123" * 4
TRAILER = "Claude" + "-Session: " + SESSION_LINK
CHAT_LINK = "https://claude" + ".ai/chat/" + "0f3c" * 4 + "-1a2b-3c4d"
FOOTER = "\U0001F916 Generated with " + "[Claude Code](https://example.com)"
COAUTHOR = "Co-Authored-By: " + "Claude Opus <noreply@example.com>"
GITHUB_TOKEN = "gh" + "p_" + "A1b2C3d4" * 5
API_KEY = "sk-" + "ant-" + "x9Y8z7W6" * 4
AWS_KEY = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"
URL_PASSWORD = "postgresql://registrar:" + "S3cretPass" + "@db.university-internal.net/banner"
SECRET_LINE = "api_key = '" + "q7Hk2Lm9Pz4Rt6" + "'"


@pytest.mark.parametrize("text,category", [
    (TRAILER, "claude_session_trailer"),
    ("see " + SESSION_LINK, "claude_session_link"),
    ("discussed in " + CHAT_LINK, "claude_conversation_link"),
    (FOOTER, "promotional_footer"),
    (COAUTHOR, "ai_coauthor_trailer"),
    ("token " + GITHUB_TOKEN, "github_token"),
    ("key " + API_KEY, "api_key"),
    ("aws " + AWS_KEY, "aws_access_key"),
    (PRIVATE_KEY, "private_key"),
    ("dsn " + URL_PASSWORD, "credential_in_url"),
    (SECRET_LINE, "secret_assignment"),
])
def test_each_kind_of_sensitive_text_is_found(text, category):
    assert category in {f.category for f in check.scan_text(text, "x:{line}")}


def test_findings_never_print_the_matched_text():
    findings = check.scan_text(f"line one\n{TRAILER}\n{API_KEY}", "msg:{line}")
    printed = "\n".join(f.line() for f in findings)
    assert "msg:2" in printed and "msg:3" in printed
    for secret in (SESSION_LINK, API_KEY, "AbC123", "x9Y8z7W6"):
        assert secret not in printed


@pytest.mark.parametrize("text", [
    "Fix the planner; see docs/workstream3-integration-audit.md, section 10.",
    "token = _RUN_LOG.set(log)",  # a variable, not a secret
    "postgresql://example-user:not-a-real-password@db.example.invalid:5432/banner",  # test fixture
    "password = '<your password here>'",
    "Claude sessions and conversations are private; never link them.",
    "AI assistance (Claude) was used for parts of this change.",  # a disclosure without a link
])
def test_ordinary_text_and_obvious_placeholders_pass(text):
    assert check.scan_text(text, "x") == []


def test_ai_coauthor_trailer_can_be_allowed_where_policy_requires_it():
    assert check.scan_text(COAUTHOR, "x", allow_ai_coauthor=True) == []


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "student@example.invalid")
    git(tmp_path, "config", "user.name", "Student")
    (tmp_path / "a.txt").write_text("start\n", encoding="utf-8")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def run_main(repo, *args):
    return check.main(["--repo", str(repo), *args])


def test_range_checks_commit_messages_and_added_lines(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text(f"start\nconfig {GITHUB_TOKEN}\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", f"Add config\n\n{TRAILER}")
    assert run_main(repo, "--range", f"{base}..HEAD") == 1
    out = capsys.readouterr().out
    assert "claude_session_trailer" in out and "github_token" in out and "a.txt:2" in out
    assert GITHUB_TOKEN not in out and SESSION_LINK not in out


def test_an_already_published_commit_can_be_acknowledged_but_new_lines_still_fail(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("start\nclean change\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", f"Change\n\n{TRAILER}")
    published = git(repo, "rev-parse", "HEAD")
    assert run_main(repo, "--range", f"{base}..HEAD", "--allow-commit", published) == 0
    assert "ACKNOWLEDGED" in capsys.readouterr().out
    (repo / "a.txt").write_text(f"start\nclean change\n{FOOTER}\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "Docs")
    assert run_main(repo, "--range", f"{base}..HEAD", "--allow-commit", published) == 1


def test_text_files_such_as_a_pr_description_are_checked(repo, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("## Summary\nAll good.\n", encoding="utf-8")
    assert run_main(repo, "--text-file", str(body)) == 0
    body.write_text(f"## Summary\nAll good.\n\n{FOOTER}\n\n{SESSION_LINK}\n", encoding="utf-8")
    assert run_main(repo, "--text-file", str(body)) == 1


def test_the_commit_msg_hook_rejects_a_private_link(repo):
    hook = check.install_hook(repo)
    if os.name != "nt":  # Git for Windows runs hooks without Unix executable bits
        assert hook.stat().st_mode & 0o100
    (repo / "a.txt").write_text("start\nmore\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    rejected = subprocess.run(["git", "commit", "-q", "-m", f"Change\n\n{TRAILER}"], cwd=repo,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert rejected.returncode != 0 and SESSION_LINK not in rejected.stdout + rejected.stderr
    git(repo, "commit", "-q", "-m", "Change without links")
    assert git(repo, "log", "-1", "--format=%s") == "Change without links"


def test_command_line_without_inputs_is_a_usage_error(repo):
    assert run_main(repo) == 2


def test_project_instructions_and_docs_contain_no_private_links_or_footers():
    files = [ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / "ai-agent" / "README.md",
             *sorted((ROOT / "docs").glob("*.md"))]
    private = {"claude_session_trailer", "claude_session_link", "claude_conversation_link", "promotional_footer",
               "ai_coauthor_trailer"}
    for f in files:
        if f.exists():
            assert [x.category for x in check.scan_text(f.read_text(encoding="utf-8"), f.name)
                    if x.category in private] == [], f.name


def test_script_runs_from_the_command_line(tmp_path):
    body = tmp_path / "body.md"
    body.write_text("Plain description.\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "ai-agent" / "dev" / "prepublish_check.py"),
                           "--text-file", str(body)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert done.returncode == 0 and "prepublish check: OK" in done.stdout


# ------------------------------------------------------------------ cross-platform (Windows CI, 2026-10-21)

def test_the_hook_is_a_posix_script_on_every_platform(repo):
    hook = check.install_hook(repo)
    raw = hook.read_bytes()
    assert b"\r\n" not in raw  # CRLF would break sh on Windows
    assert raw.startswith(b"#!/bin/sh\n") and b"\\" not in raw  # forward slashes only
    assert check.install_hook(repo) == hook  # installing again is idempotent


def test_unicode_in_commit_messages_and_files_is_read_as_utf8(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "notes.md").write_text("caf\u00e9 \u2713 \u0645\u0631\u062d\u0628\u0627\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    git(repo, "commit", "-q", "-m", f"Notes \u2713\n\n{FOOTER}")
    findings, commits, added = check.scan_range(f"{base}..HEAD", set(), cwd=repo)
    assert commits == 1 and added == 1
    assert [(f.category, f.location.startswith("commit")) for f in findings] == [("promotional_footer", True)]
    body = tmp_path / "unicode-body.md"
    body.write_text("Clean description \u2713 \u0645\u0631\u062d\u0628\u0627\n", encoding="utf-8")
    assert run_main(repo, "--text-file", str(body)) == 0
