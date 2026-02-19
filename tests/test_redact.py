from __future__ import annotations

import pytest

from convx_ai.redact import REDACTED, redact_secrets


def test_redact_disabled() -> None:
    assert redact_secrets("sk-proj-abc123xyz", redact=False) == "sk-proj-abc123xyz"


def test_openai_project_key() -> None:
    text = "Use API key sk-proj-redact-test-abc123xyz for the demo."
    assert REDACTED in redact_secrets(text)
    assert "sk-proj-redact-test-abc123xyz" not in redact_secrets(text)


def test_openai_legacy_key() -> None:
    text = "sk-abcdefghijklmnopqrstuvwxyz123456"
    assert redact_secrets(text) == REDACTED


def test_aws_key() -> None:
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    out = redact_secrets(text)
    assert REDACTED in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_github_token() -> None:
    text = "ghp_" + "x" * 36
    assert redact_secrets(text) == REDACTED


def test_stripe_key() -> None:
    text = "sk_live_" + "0" * 24
    assert redact_secrets(text) == REDACTED


def test_slack_token() -> None:
    text = "xoxb-1234-5678-abcdefghijkl"
    assert redact_secrets(text) == REDACTED


def test_slack_webhook() -> None:
    text = "https://hooks.slack.com/services/T123/B456/abc123"
    assert redact_secrets(text) == REDACTED


def test_sendgrid_key() -> None:
    text = "SG." + "a" * 22 + "." + "b" * 43
    assert redact_secrets(text) == REDACTED


def test_private_key_rsa() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----"
    assert redact_secrets(text) == REDACTED


def test_private_key_ec() -> None:
    text = "-----BEGIN EC PRIVATE KEY-----"
    assert redact_secrets(text) == REDACTED


def test_private_key_openssh() -> None:
    text = "-----BEGIN OPENSSH PRIVATE KEY-----"
    assert redact_secrets(text) == REDACTED


def test_multiple_secrets() -> None:
    secret1 = "sk-proj-" + "a" * 20
    secret2 = "sk-proj-" + "b" * 20
    text = f"key1={secret1} key2={secret2}"
    out = redact_secrets(text)
    assert secret1 not in out and secret2 not in out
    assert out.count(REDACTED) == 2


def test_no_false_positive_urls() -> None:
    text = "https://example.com/path?param=value"
    assert redact_secrets(text) == text


def test_no_false_positive_short_sk() -> None:
    text = "sk-abc"
    assert redact_secrets(text) == text


def test_no_false_positive_ghp_prefix() -> None:
    text = "ghp_short"
    assert redact_secrets(text) == text


def test_google_api_key() -> None:
    text = "AIza" + "a" * 35
    assert redact_secrets(text) == REDACTED


def test_twilio_key() -> None:
    text = "SK" + "a" * 32
    assert redact_secrets(text) == REDACTED


def test_telegram_bot_token() -> None:
    text = "12345:AA" + "a" * 33
    assert redact_secrets(text) == REDACTED
