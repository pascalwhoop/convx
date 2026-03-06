# Conversation Exporter

Export AI conversation sessions into a Git repository using a readable, time-based structure.

![](docs/assets/cast.gif)

## What it does

- Scans source session files (Codex JSONL, Claude projects, Cursor workspaceStorage, Gemini CLI sessions).
- Normalizes each session into a common model.
- Writes two artifacts per session:
    - readable Markdown transcript: `YYYY-MM-DD-HHMM-slug.md`
    - hidden normalized JSON: `.YYYY-MM-DD-HHMM-slug.json`
- Organizes history by user and source system:
    - `sync`: `.ai/history/<user>/<source-system>/` (flat — sessions directly inside)
    - `backup`: `history/<user>/<source-system>/<system-name>/<path-relative-to-home>/...`
- Runs idempotently (only reprocesses changed or new sessions).
- Cursor: supports both single-folder and multi-root (`.code-workspace`) windows — sessions are attributed to the matching repo folder.

## TL;DR

No install needed — just run from any project folder:

```bash
uvx --from convx-ai convx sync
```

## Install and run

```bash
uv add convx-ai
# or: pip install convx-ai
convx --help
```

From source:

```bash
uv sync
uv run convx --help
```

## sync — project-scoped command

Run from inside any Git repo. Syncs conversations for the current folder by default and writes
them into the repo itself:

```bash
cd /path/to/your/project
uv run convx sync
```

By default syncs Codex, Claude, Cursor, and Gemini. Use `--source-system codex`, `--source-system claude`, `--source-system cursor`, or `--source-system gemini` to sync a single source. No `--output-path` needed — the Git root is used as destination and the current working directory is used as scope filter. Recursive folder matching is enabled by default; use `--no-recursive` to restrict to the current folder only. Sessions are written flat under `.ai/history/<user>/<source-system>/` with no machine name or path nesting.

## backup — full backup command

Exports all conversations into a dedicated backup Git repo:

```bash
uv run convx backup \
  --output-path /path/to/your/backup-git-repo \
  --source-system codex
```

## Common options

- `--source-system`: source(s) to sync: `all` (default), `codex`, `claude`, `cursor`, `gemini`, or comma-separated.
- `--input-path`: source sessions directory override (per source).
    - default for Codex: `~/.codex/sessions`
    - default for Claude: `~/.claude/projects`
    - default for Cursor: `~/Library/Application Support/Cursor/User/workspaceStorage` (macOS)
      Supports both single-folder and multi-root (`.code-workspace`) Cursor windows.
    - default for Gemini: `~/.gemini/tmp`
- `--user`: user namespace for history path (default: current OS user).
- `--system-name`: system namespace for history path (default: hostname).
- `--dry-run`: discover and plan without writing files.
- `--history-subpath`: folder inside output repo where history is stored (default: `sync` = `.ai/history`, `backup` = `history`).
- `--recursive` / `--no-recursive` (`sync` only): include or exclude subdirectories of the current folder (default: `--recursive`).
- `--output-path` (backup only): target Git repository (must already contain `.git`).

## Configuration defaults

Set repo-level defaults in `.convx/config.toml`. CLI flags override config values.

```toml
[sync]
history_subpath = ".ai/history"
skip_if_contains = "CONVX_NO_SYNC"
redact = true

[backup]
history_subpath = "history"
redact = true

[sanitize]
keywords = ["work", "client-x"]
```

## Example output

`convx sync` (inside a project repo):

```text
history/
  pascal/
    codex/
      2026-02-15-1155-conversation-backup-plan.md
      .2026-02-15-1155-conversation-backup-plan.json
    claude/
      2026-01-15-1000-api-auth-migration-plan/
        index.md
        agent-abc1234.md
        .index.json
```

`convx backup` (dedicated backup repo):

```text
history/
  pascal/
    codex/
      macbook-pro/
        Code/
          my-project/
            prototypes/
              matrix-heatmap-test/
                2026-02-15-1155-conversation-backup-plan.md
                .2026-02-15-1155-conversation-backup-plan.json
```

## Idempotency behavior

- Export state is stored at `.convx/index.json` in the output repo.
- A session is skipped when both:
    - `session_key` already exists, and
    - source fingerprint (SHA-256 of source file) is unchanged.
- If source content changes, that session is re-rendered in place.

## Other commands

**stats** — index totals and last update time:

```bash
uv run convx stats --output-path /path/to/your/backup-git-repo
```

**explore** — browse and search exported conversations in a TUI:

```bash
uv run convx explore --output-path /path/to/your/repo
```

**hooks** — install or remove a pre-commit hook that runs sync before each commit:

```bash
uv run convx hooks install
uv run convx hooks uninstall
```

## Secrets

Exports are redacted by default (API keys, tokens, passwords → `[REDACTED]`). Be mindful of secrets in your history repo. See [docs/secrets.md](docs/secrets.md) for details and pre-commit scanner options (Gitleaks, TruffleHog, detect-secrets, semgrep).
