from __future__ import annotations

import json

from convx_ai.models import NormalizedSession


def first_user_text(session: NormalizedSession) -> str:
    for message in session.messages:
        if message.kind == "user" and message.text.strip():
            return message.text.strip()
    return ""


def _html_comment(content: str) -> str:
    # Escape any accidental comment-close sequence so the block stays valid.
    safe = content.replace("-->", "-- >")
    return f"<!--\n{safe}\n-->"


def render_markdown(
    session: NormalizedSession,
    *,
    with_context: bool = False,
    with_thinking: bool = False,
) -> str:
    lines: list[str] = []
    lines.append(f"# Conversation {session.session_id}")
    lines.append("")
    lines.append(f"- Source: `{session.source_system}`")
    lines.append(f"- User: `{session.user}`")
    lines.append(f"- System: `{session.system_name}`")
    lines.append(f"- Started: `{session.started_at}`")
    lines.append(f"- CWD: `{session.cwd or '(unknown)'}`")
    lines.append("")

    visible = [m for m in session.messages if m.kind in {"user", "assistant"}]
    if not visible:
        lines.append("_No user/assistant messages extracted._")
        lines.append("")

    for message in session.messages:
        if message.kind in {"system", "tool"}:
            if not with_context:
                continue
            label = message.role.upper()
            ts = f" ({message.timestamp})" if message.timestamp else ""
            inner = f"### {label}{ts}\n\n{message.text}"
            lines.append(_html_comment(inner))
            lines.append("")
        elif message.kind == "thinking":
            if not with_thinking:
                continue
            label = message.role.upper()
            ts = f" ({message.timestamp})" if message.timestamp else ""
            inner = f"### {label}{ts}\n\n{message.text}"
            lines.append(_html_comment(inner))
            lines.append("")
        elif message.kind == "user":
            ts = f"\n\n_`{message.timestamp}`_" if message.timestamp else ""
            lines.append(f"## User{ts}")
            lines.append("")
            lines.append(message.text)
            lines.append("")
        elif message.kind == "assistant":
            ts = f"\n\n_`{message.timestamp}`_" if message.timestamp else ""
            lines.append(f"## Agent{ts}")
            lines.append("")
            lines.append(message.text)
            lines.append("")

    return "\n".join(lines)


def render_json(session: NormalizedSession) -> str:
    return json.dumps(session.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
