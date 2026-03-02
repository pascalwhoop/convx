# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Commands

```bash
uv sync                   # install dependencies
uv run convx --help       # run CLI
uv run pytest             # run all tests
uv run pytest tests/test_integration_sync.py::test_name  # run a single test
```

## Architecture

`convx` (convx-ai) exports AI session files into a Git repository as Markdown transcripts + hidden JSON blobs.

**Data flow:**
1. **Adapter** (`src/convx_ai/adapters/`) — discovers and parses source files into `NormalizedSession` / `NormalizedMessage` models. Adapters: Codex (`~/.codex/sessions`), Claude (`~/.claude/projects`), Cursor (workspaceStorage).
2. **Engine** (`engine.py`) — `sync_sessions()` orchestrates idempotency: loads `.convx/index.json`, fingerprints source files (SHA-256), skips unchanged sessions, calls the adapter to parse changed ones, then writes artifacts and updates the index.
3. **Render** (`render.py`) — converts `NormalizedSession` to Markdown transcript or JSON string.
4. **CLI** (`cli.py`) — two main commands built with Typer:
   - `sync`: runs inside a project repo, filters sessions by `cwd`, writes flat under `.ai/history/<user>/<source>/` by default
   - `backup`: writes to a dedicated repo with full path nesting `history/<user>/<source>/<system>/<relative-cwd>/`

**Idempotency index:** `.convx/index.json` in the output repo. Keyed by `session_key` (`<source_system>:<session_id>`). A session is re-exported only when the source SHA-256 changes or output files are missing.

**Adding a new source system adapter:** implement `discover_files(input_path)`, `peek_session(source_path, source_system)`, and `parse_session(...)` → `NormalizedSession`, then register in `adapters/__init__.py`.

**`NormalizedMessage.kind`** distinguishes rendering roles: `"user"` | `"assistant"` | `"system"` | `"tool"`. In the Codex adapter, `role="user"` messages are classified as `kind="system"` when the text wasn't typed by the human (injected context vs. actual user input).

## Line-Level Content Sanitization

**Feature:** Replace entire lines containing sensitive keywords with `[SANITIZED]` to exclude work/client content from exported history.

**Configuration:** Create `.convx/config.toml` in the output repo:

```toml
[sanitize]
# Lines containing any of these terms will be replaced with [SANITIZED]
keywords = ["work", "sensitive topic ", "some rant"]
```

**How it works:**
- Loaded automatically on every `sync` or `backup` run
- Applied **after** secret redaction (API keys, tokens, passwords)
- Matching is **case-insensitive** (e.g., `"PONY"` matches `pony`, `Pony`)
- Each entire line is replaced; no partial leaks
- File can be committed to share team defaults, or ignored for per-user setup

**Integration:** `sanitize.py` exports:
- `load_sanitize_keywords(repo_path: Path) -> list[str]` — reads `.convx/config.toml` (`[sanitize].keywords`)
- `sanitize_lines(text: str, keywords: list[str]) -> str` — replaces matching lines

Called in `engine.py` after every `redact_secrets()` call (markdown, JSON, child sessions).

## Force Overwrite (Idempotency Override)

**Feature:** Re-export all sessions, ignoring cached fingerprints, to reprocess previously exported data with new redaction/sanitization rules.

**Usage:**
```bash
convx sync --overwrite           # Sync with force-overwrite
convx backup --output-path ~/my-history --overwrite
```

**How it works:**
- Bypasses fingerprint check in `engine.py:140`
- All sessions are re-exported and re-sanitized
- Useful after adding new keywords to `.convx/config.toml` to clean old exports
- Index is still updated normally; subsequent runs without `--overwrite` skip unchanged sessions
