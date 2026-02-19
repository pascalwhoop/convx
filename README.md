# Conversation Exporter

Export AI conversation sessions into a Git repository using a readable, time-based structure.

## What it does

- Scans source session files (Codex JSONL, Claude projects, Cursor workspaceStorage).
- Normalizes each session into a common model.
- Writes two artifacts per session:
    - readable Markdown transcript: `YYYY-MM-DD-HHMM-slug.md`
    - hidden normalized JSON: `.YYYY-MM-DD-HHMM-slug.json`
- Organizes history by user and source system:
    - `sync`: `history/<user>/<source-system>/` (flat — sessions directly inside)
    - `backup`: `history/<user>/<source-system>/<system-name>/<path-relative-to-home>/...`
- Runs idempotently (only reprocesses changed or new sessions).

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

Run from inside any Git repo. Syncs only the conversations that took place in that repo (or its
subfolders) and writes them into the repo itself:

```bash
cd /path/to/your/project
uv run convx sync
```

By default syncs Codex, Claude, and Cursor. Use `--source-system codex`, `--source-system claude`, or `--source-system cursor` to sync a single source. No `--output-path` needed — the current directory is used as both the filter and the destination. Sessions are written flat under `history/<user>/<source-system>/` with no machine name or path nesting.

## backup — full backup command

Exports all conversations into a dedicated backup Git repo:

```bash
uv run convx backup \
  --output-path /path/to/your/backup-git-repo \
  --source-system codex
```

## Common options

- `--source-system`: source(s) to sync: `all` (default), `codex`, `claude`, `cursor`, or comma-separated.
- `--input-path`: source sessions directory override (per source).
    - default for Codex: `~/.codex/sessions`
    - default for Claude: `~/.claude/projects`
    - default for Cursor: `~/Library/Application Support/Cursor/User/workspaceStorage` (macOS)
- `--user`: user namespace for history path (default: current OS user).
- `--system-name`: system namespace for history path (default: hostname).
- `--dry-run`: discover and plan without writing files.
- `--history-subpath`: folder inside output repo where history is stored (default `history`).
- `--output-path` (backup only): target Git repository (must already contain `.git`).

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
          everycure/
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
