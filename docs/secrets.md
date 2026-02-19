# Secret redaction

convx redacts API keys, tokens, passwords, and similar secrets from exported files so they don't end up in your history repo.

> ⚠️ You are responsible for ensuring no secrets are committed; we provide no warranty or liability.

## User perspective

- **Default:** Redaction is **on**. Exported Markdown and JSON are scrubbed before writing.
- **Disable:** Use `--no-redact` on `sync` or `backup` if you need the raw content (e.g. local-only, debugging).

  ```bash
  convx sync --no-redact
  convx backup --output-path /path/to/repo --no-redact
  ```

- **What gets redacted:** API keys (OpenAI, AWS, Stripe, GitHub, etc.), tokens, passwords, private keys, and similar credentials. Matched secrets are replaced with `[REDACTED]`.
- **What you see:** All redacted values appear as `[REDACTED]` in the written files.

## How it works technically

- **Library:** [Hyperscan](https://github.com/intel/hyperscan) via [python-hyperscan](https://github.com/darvid/python-hyperscan) — multi-pattern matching with `HS_FLAG_UTF8` and `HS_FLAG_SOM_LEFTMOST` so we get correct start/end spans. Text is scanned as UTF-8 bytes; match spans are merged when overlapping, then replaced from end to start so indices stay valid. All matches become `[REDACTED]`.
- **When:** Redaction runs **after** rendering and **before** writing. Both Markdown and JSON outputs are passed through `redact_secrets()` in the engine; the index (`.convx/index.json`) is not redacted.
- **Where in code:** `convx_ai.redact.redact_secrets(text, redact=True)`. The engine calls it for every session markdown and JSON blob when `redact=True`; the CLI passes `redact=not no_redact` from `sync` and `backup`.
- **Patterns:** Curated regex set in `convx_ai.redact_patterns` (OpenAI, AWS, GitHub, Stripe, Slack, SendGrid, Discord, Google, Twilio, Telegram, Square, private keys, etc.). No entropy-based detection (avoids over-redacting URLs and long IDs in transcripts). Patterns must be Hyperscan-compatible (no backrefs, no lookahead/lookbehind).

## Pattern sources

Default patterns are derived from:

- [mazen160/secrets-patterns-db](https://github.com/mazen160/secrets-patterns-db) — high-confidence and rules-stable datasets (1,600+ patterns, ReDoS-tested)
- [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) — `config/gitleaks.toml` built-in rules
- [Yelp/detect-secrets](https://github.com/Yelp/detect-secrets) — plugin regex patterns

To add or change patterns, edit `src/convx_ai/redact_patterns.py`. Each entry is `(bytes_regex, unique_id)`; regex syntax is Hyperscan’s (PCRE-like, no backrefs/lookahead/lookbehind).

## Pre-commit secret scanners (defense in depth)

For additional protection, add a pre-commit hook to block secrets before they enter your repo. Popular options:

| Tool | Language | Engine | Notes |
|-----|----------|--------|-------|
| **Gitleaks** | Go | RE2 | Single-pass scan, huge maintained pattern DB. Most popular pre-commit tool. |
| **TruffleHog** | Go | RE2 | Similar to Gitleaks, strong verification and pattern coverage. |
| **detect-secrets** | Python | regex | Yelp's tool, what most Python shops use in CI. Baseline-based. |
| **semgrep** | OCaml | custom | AST-aware, more than regex. Heavily used in enterprise CI. |

### Example configs

**Gitleaks** (recommended):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

**TruffleHog**:

```yaml
repos:
  - repo: https://github.com/trufflesecurity/trufflehog
    rev: v3.78.0
    hooks:
      - id: trufflehog
```

**detect-secrets** (Python shops):

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

Create a baseline with `detect-secrets scan > .secrets.baseline` before first use.

**semgrep** (enterprise / AST-aware):

```yaml
repos:
  - repo: https://github.com/semgrep/pre-commit
    rev: v1.151.0
    hooks:
      - id: semgrep
        args: ['--config', 'p/secrets', '--error']
```
