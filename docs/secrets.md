# Secret redaction

convx redacts API keys, tokens, passwords, and similar secrets from exported files so they don’t end up in your history repo. 

> ⚠️ You are responsible for ensuring no secrets are committed; we provide no warranty or liability.

## User perspective

- **Default:** Redaction is **on**. Exported Markdown and JSON are scrubbed before writing.
- **Disable:** Use `--no-redact` on `sync` or `backup` if you need the raw content (e.g. local-only, debugging).

  ```bash
  convx sync --no-redact
  convx backup --output-path /path/to/repo --no-redact
  ```

- **What gets redacted:** Patterns for credentials and secrets (e.g. OpenAI-style keys, `api_key=...`, `password=...`, AWS/GCP/Stripe/GitHub tokens). High-entropy but non-secret text (URLs, long IDs) is left as-is.
- **What you see:** Matched secrets are replaced with markers like `[REDACTED:api_key]` or `[REDACTED:password]` in the written files.

## How it works technically

- **Library:** [plumbrc](https://pypi.org/project/plumbrc/) — pattern-based redaction (700+ built-in patterns). If plumbrc isn’t available at runtime, redaction is skipped and content is written unchanged.
- **When:** Redaction runs **after** rendering and **before** writing. Both Markdown and JSON outputs are passed through `redact_secrets()` in the engine; the index (`.convx/index.json`) is not redacted.
- **Where in code:** `convx_ai.redact.redact_secrets(text, redact=True)` wraps `Plumbr(quiet=True).redact(text)`. The engine calls it for every session markdown and JSON blob (including child-session markdown) when `redact=True`; the CLI passes `redact=not no_redact` from `sync` and `backup`.
