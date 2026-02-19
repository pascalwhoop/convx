"""
Secret detection patterns for redaction.

Hyperscan-compatible: no backrefs, no lookahead/lookbehind.
Patterns match the secret value only (no surrounding context).

Sources:
- mazen160/secrets-patterns-db (high-confidence, rules-stable)
- gitleaks/gitleaks config
- Yelp/detect-secrets plugins
"""

# (pattern, id) — ids must be unique
PATTERNS: list[tuple[bytes, int]] = [
    # OpenAI (detect-secrets, custom)
    (br"sk-proj-[a-zA-Z0-9_-]{20,}", 0),
    (br"sk-[a-zA-Z0-9_-]{20,}", 1),
    (br"sk-[A-Za-z0-9-_]*[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}", 2),
    # AWS (secrets-patterns-db, gitleaks)
    (br"AKIA[0-9A-Z]{16}", 3),
    (br"ASIA[0-9A-Z]{16}", 4),
    (br"da2-[a-z0-9]{26}", 5),
    # GitHub (detect-secrets)
    (br"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}", 6),
    # Stripe (secrets-patterns-db)
    (br"sk_live_[0-9a-zA-Z]{24}", 7),
    (br"rk_live_[0-9a-zA-Z]{24}", 8),
    # Slack (detect-secrets — flexible format)
    (br"xox(?:a|b|p|o|s|r)-(?:\d+-)+[a-zA-Z0-9]+", 9),
    (br"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+", 10),
    # SendGrid (detect-secrets)
    (br"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}", 11),
    # Discord (detect-secrets)
    (br"[MNO][a-zA-Z0-9_-]{23,25}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}", 12),
    # Google (secrets-patterns-db)
    (br"AIza[0-9A-Za-z_-]{35}", 13),
    (br"ya29\.[0-9A-Za-z_-]+", 14),
    # Twilio (secrets-patterns-db)
    (br"SK[0-9a-fA-F]{32}", 15),
    # Telegram (secrets-patterns-db)
    (br"[0-9]+:AA[0-9A-Za-z_-]{33}", 16),
    # Mailgun, Mailchimp (secrets-patterns-db)
    (br"key-[0-9a-zA-Z]{32}", 17),
    (br"[0-9a-f]{32}-us[0-9]{1,2}", 18),
    # Square (secrets-patterns-db)
    (br"sq0atp-[0-9A-Za-z_-]{22}", 19),
    (br"sq0csp-[0-9A-Za-z_-]{43}", 20),
    # Private keys (secrets-patterns-db, detect-secrets)
    (br"-----BEGIN RSA PRIVATE KEY-----", 21),
    (br"-----BEGIN DSA PRIVATE KEY-----", 22),
    (br"-----BEGIN EC PRIVATE KEY-----", 23),
    (br"-----BEGIN OPENSSH PRIVATE KEY-----", 24),
    (br"-----BEGIN PGP PRIVATE KEY BLOCK-----", 25),
    (br"-----BEGIN PRIVATE KEY-----", 26),
]
