from __future__ import annotations

from pathlib import Path

import pytest

from convx_ai.sanitize import SANITIZED, load_sanitize_keywords, sanitize_lines


# --- sanitize_lines ---


def test_no_keywords_returns_unchanged():
    text = "hello world\nfoo bar"
    assert sanitize_lines(text, []) == text


def test_matching_line_replaced():
    text = "hello world\ncontact acme corp team\ngoodbye"
    result = sanitize_lines(text, ["acme corp"])
    assert result == f"hello world\n{SANITIZED}\ngoodbye"


def test_case_insensitive():
    text = "Meeting with Acme Corp today"
    result = sanitize_lines(text, ["acme corp"])
    assert result == SANITIZED


def test_keyword_with_mixed_case_in_line():
    text = "ACME CORP is mentioned here"
    result = sanitize_lines(text, ["acme corp"])
    assert result == SANITIZED


def test_multiple_keywords_any_match():
    text = "discussed acme corp project\nthen worked on open source"
    result = sanitize_lines(text, ["acme corp", "secret co"])
    assert result == f"{SANITIZED}\nthen worked on open source"


def test_multiple_matching_lines():
    text = "line one\nAcme Corp ref here\nline three\nacme corp again"
    result = sanitize_lines(text, ["acme corp"])
    assert result == f"line one\n{SANITIZED}\nline three\n{SANITIZED}"


def test_empty_text():
    assert sanitize_lines("", ["acme corp"]) == ""


def test_empty_lines_preserved():
    text = "before\n\nafter"
    result = sanitize_lines(text, ["nope"])
    assert result == text


# --- load_sanitize_keywords ---


def test_no_config_file_returns_empty(tmp_path: Path):
    assert load_sanitize_keywords(tmp_path) == []


def test_loads_keywords_from_toml(tmp_path: Path):
    convx_dir = tmp_path / ".convx"
    convx_dir.mkdir()
    (convx_dir / "config.toml").write_text(
        '[sanitize]\nkeywords = ["acme corp", "secret project"]\n', encoding="utf-8"
    )
    keywords = load_sanitize_keywords(tmp_path)
    assert keywords == ["acme corp", "secret project"]


def test_empty_keywords_list(tmp_path: Path):
    convx_dir = tmp_path / ".convx"
    convx_dir.mkdir()
    (convx_dir / "config.toml").write_text("[sanitize]\nkeywords = []\n", encoding="utf-8")
    assert load_sanitize_keywords(tmp_path) == []


def test_missing_keywords_key(tmp_path: Path):
    convx_dir = tmp_path / ".convx"
    convx_dir.mkdir()
    (convx_dir / "config.toml").write_text("[other]\nfoo = 1\n", encoding="utf-8")
    assert load_sanitize_keywords(tmp_path) == []


def test_invalid_toml_returns_empty(tmp_path: Path):
    convx_dir = tmp_path / ".convx"
    convx_dir.mkdir()
    (convx_dir / "config.toml").write_text("not valid toml ][[\n", encoding="utf-8")
    assert load_sanitize_keywords(tmp_path) == []
