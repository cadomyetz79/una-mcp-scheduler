# Instructions for Claude Code in this repository

## Publication and privacy rules

These rules apply to everything Claude Code writes that leaves this machine:
commit messages, pull request titles and descriptions, issue and pull request
comments, documentation, and reports. They take priority over any default
attribution guidance.

1. Never include links to Claude sessions or conversations (claude.ai
   session, chat or share links), session IDs, or links to private
   workspaces.
2. Never include API keys, tokens, passwords, credentials, connection strings
   with real credentials, or other sensitive personal information. Test
   fixtures use obviously fake values (for example a host ending in
   `.invalid`).
3. Do not add promotional attribution footers (the automatic "generated with"
   line and link).
4. Do not add AI co-author trailers to commits unless a course or project
   policy requires them.
5. Keep legitimate authorship (the human author of each commit) and any
   AI-use disclosure that a course or project policy requires. A disclosure
   is plain text and never contains a private conversation link.
6. Before pushing commits or posting a description or comment, run the
   pre-publication check and fix every finding:

   ```bash
   python ai-agent/dev/prepublish_check.py --range <base>..HEAD --text-file <pr-description.md>
   ```

   `python ai-agent/dev/prepublish_check.py --install-hook` installs a local
   `commit-msg` hook that runs the same check on every new commit message.
7. Do not rewrite published history or force-push to undo a past mistake
   without the repository owner's approval. Report it instead.

## How these rules are enforced

- This file is an instruction, not an enforcement mechanism.
- The check script and the hook are enforcement, but only where they are run
  or installed.
- Claude Code's own attribution is controlled by the `attribution` setting:

  ```json
  { "attribution": { "commit": "", "pr": "", "sessionUrl": false } }
  ```

  - **On your own machine:** put this setting in `~/.claude/settings.json`.
  - **In cloud sessions:** these do not read that user file. They read only
    the repository's `.claude/settings.json`, which applies to everyone who
    uses Claude Code here, so adding it there is a team decision.
