from __future__ import annotations

from pathlib import Path

from convx_ai.config import ConvxConfig

SANITIZED = "[SANITIZED]"


def load_sanitize_keywords(repo_path: Path) -> list[str]:
    """Load keyword list from .convx/config.toml in the output repo.

    Returns an empty list if the file does not exist or contains no keywords.
    """
    return [k for k in ConvxConfig.for_repo(repo_path).sanitize.keywords if k]


def sanitize_lines(text: str, keywords: list[str]) -> str:
    """Replace any line containing a keyword (case-insensitive) with [SANITIZED]."""
    if not keywords:
        return text
    lower_keywords = [k.lower() for k in keywords]
    lines = text.split("\n")
    result = []
    for line in lines:
        if any(kw in line.lower() for kw in lower_keywords):
            result.append(SANITIZED)
        else:
            result.append(line)
    return "\n".join(result)
