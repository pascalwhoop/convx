from __future__ import annotations

import hyperscan

from convx_ai.redact_patterns import PATTERNS

REDACTED = "[REDACTED]"

_db: hyperscan.Database | None = None


def _get_db() -> hyperscan.Database:
    global _db
    if _db is None:
        exprs, ids = zip(*PATTERNS)
        _db = hyperscan.Database()
        _db.compile(
            expressions=list(exprs),
            ids=list(ids),
            elements=len(PATTERNS),
            flags=[hyperscan.HS_FLAG_UTF8 | hyperscan.HS_FLAG_SOM_LEFTMOST] * len(PATTERNS),
        )
    return _db


def _merge_overlaps(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    sorted_spans = sorted(spans)
    merged = [sorted_spans[0]]
    for start, end in sorted_spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def redact_secrets(text: str, *, redact: bool = True) -> str:
    if not redact:
        return text
    data = text.encode("utf-8")
    matches: list[tuple[int, int]] = []

    def on_match(id: int, from_: int, to: int, flags: int, context: list) -> None:
        context.append((from_, to))

    _get_db().scan(data, match_event_handler=on_match, context=matches)
    spans = _merge_overlaps(matches)

    for start, end in sorted(spans, key=lambda s: -s[1]):
        char_start = len(data[:start].decode("utf-8"))
        char_end = len(data[:end].decode("utf-8"))
        text = text[:char_start] + REDACTED + text[char_end:]
    return text
