from __future__ import annotations

try:
    from plumbrc import Plumbr
    _plumbr_available = True
except Exception:
    Plumbr = None
    _plumbr_available = False


def redact_secrets(text: str, *, redact: bool = True) -> str:
    if not redact:
        return text
    if not _plumbr_available:
        return text
    return Plumbr(quiet=True).redact(text)
