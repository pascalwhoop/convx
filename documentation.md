# Developer Documentation

This document explains the internal architecture and sync behavior.

## Commands

- `sync` — run from inside a project repo; syncs only conversations from that repo into it.
- `backup` — full export of all conversations into a dedicated backup repo (`--output-path` required).
- `stats` — shows index totals for a given repo.

## Architecture

The exporter is split into four layers:

1. `cli.py`
   - Typer entrypoint and option parsing.
2. `adapters/`
   - Source-specific parsing and normalization.
   - `codex.py` currently implements Codex JSONL ingestion.
3. `engine.py`
   - Idempotent sync loop, index management, path mapping, and output writes.
4. `render.py`
   - Markdown transcript rendering and JSON serialization.

## Normalized session model

`NormalizedSession` stores:

- source metadata (`source_system`, `session_id`, `source_path`)
- routing metadata (`user`, `system_name`, `cwd`, `started_at`)
- content (`messages`)
- stable key (`session_key`)

`NormalizedMessage` stores:

- `role`
- `text`
- optional `timestamp`

This model lets additional adapters (Claude, Gemini, etc.) plug in without changing engine/output logic.

## Path mapping

**`backup`** (full export):

`history/<user>/<source-system>/<system-name>/<cwd-relative-to-home>/`

- If `cwd` is under `/Users/<name>/`, path is made relative to that home.
- If `cwd` is under `/home/<name>/`, path is made relative to that home.
- Otherwise, the absolute path is sanitized and used.
- Path segments are sanitized to filesystem-safe slugs.

**`sync`** (repo-scoped):

`history/<user>/<source-system>/`

Sessions are written flat — no machine name or cwd nesting.

## File naming

Basename:

`YYYY-MM-DD-HHMM-<slug>`

Where:

- date/time is from session start timestamp (`session_meta.payload.timestamp` fallback to event timestamp)
- slug is derived from first user message text (fallback to session id tail)

Outputs per session:

- Markdown transcript: `<basename>.md`
- Hidden normalized JSON: `.<basename>.json`

## Idempotency and index

Index location:

`<output-repo>/.convx/index.json`

Index record per session key:

- `fingerprint`: SHA-256 of source file bytes
- `source_path`
- `markdown_path`
- `json_path`
- `basename`
- `updated_at`

Sync algorithm:

1. Discover candidate session files with adapter.
2. Compute source fingerprint.
3. Peek session key (cheap first-line parse).
4. If key exists and fingerprint unchanged, skip.
5. Else parse + normalize + render + overwrite output files atomically.
6. Update index atomically.

Repo-scoped sync (`sync`):

- Auto-detects the current working directory as the git repo (`repo_filter_path=cwd`).
- A session is eligible when its `cwd` resolves under the repo path.
- Fallback matching also accepts sessions whose `cwd` contains the repo folder name (for cross-machine path differences).
- Conversations are written into the same repo they are filtered by.

Atomic writing:

- write `*.tmp`
- `Path.replace()` into final file

## Extending with new systems

Implement a new adapter that exposes:

- `discover_files(input_path)`
- `peek_session(file_path, source_system)`
- `parse_session(file_path, source_system, user, system_name)`

Then register it in `adapters/__init__.py`.
