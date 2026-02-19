# Conversation 8755a4c9-6376-460e-b203-e64e0febd6b5

- Source: `cursor`
- User: `pascal`
- System: `Pascals-MBP.local`
- Started: `2026-02-19T19:00:12.687000Z`
- CWD: `/Users/pascal/Code/business/convx`

## User

can you help why convx CLI is not in path after I do uv sync?

## Agent

Checking how the convx CLI is configured in the project.

## Agent

`uv sync` installs the project into a virtual environment (usually `.venv/`) but does **not** add it to your PATH or activate it.

You can use `convx` in three ways:

1. **`uv run convx`** (recommended) – runs the CLI in the project’s venv without activating it:
   ```bash
   uv run convx --help
   ```

2. **Activate the venv first** – then `convx` is on PATH:
   ```bash
   source .venv/bin/activate
   convx --help
   ```

3. **Call the script directly**:
   ```bash
   .venv/bin/convx --help
   ```

For day-to-day use, `uv run convx` is usually best because it always uses the correct environment and doesn’t require activation.
