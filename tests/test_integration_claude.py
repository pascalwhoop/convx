from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "claude_projects"


def _encode_path(p: Path) -> str:
    s = str(p.resolve()).replace("/", "-")
    return s if s.startswith("-") else f"-{s}"


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1"}
    return subprocess.run(
        [sys.executable, "-m", "conversation_exporter", *args],
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_backup_counts(stdout: str, exported: int | None = None, skipped: int | None = None) -> None:
    if exported is not None:
        assert re.search(rf"Exported\s+{exported}\b", stdout), f"Expected Exported {exported} in {stdout!r}"
    if skipped is not None:
        assert re.search(rf"Skipped\s+{skipped}\b", stdout), f"Expected Skipped {skipped} in {stdout!r}"


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)


def _setup_claude_fixtures(tmp_path: Path, repo_path: Path) -> Path:
    """Create Claude project dirs under tmp_path that match repo_path. Returns projects dir."""
    projects_dir = tmp_path / "claude_projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    encoded = _encode_path(repo_path)
    encoded_api = f"{encoded}-api"
    encoded_other = "-Users-alice-Code-other"

    def write_backend_project():
        proj = projects_dir / encoded
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "sessions-index.json").write_text(json.dumps({
            "version": 1,
            "entries": [
                {
                    "sessionId": "aaaaaaaa-1111-2222-3333-444444440001",
                    "fileMtime": 1700000001000,
                    "summary": "API Auth Migration Plan",
                    "created": "2026-01-15T10:00:00.000Z",
                    "modified": "2026-01-15T10:05:00.000Z",
                    "projectPath": str(repo_path),
                    "isSidechain": False,
                },
                {
                    "sessionId": "bbbbbbbb-1111-2222-3333-444444440002",
                    "fileMtime": 1700000002000,
                    "summary": "Health Check Endpoint",
                    "created": "2026-01-15T11:00:00.000Z",
                    "modified": "2026-01-15T11:01:00.000Z",
                    "projectPath": str(repo_path),
                    "isSidechain": False,
                },
            ],
            "originalPath": str(repo_path),
        }, indent=2))
        (proj / "aaaaaaaa-1111-2222-3333-444444440001.jsonl").write_text(
            '{"type":"user","cwd":"' + str(repo_path) + '","sessionId":"aaaaaaaa-1111-2222-3333-444444440001","message":{"role":"user","content":"Plan migration for API auth."},"timestamp":"2026-01-15T10:00:00.000Z"}\n'
            '{"type":"assistant","cwd":"' + str(repo_path) + '","sessionId":"aaaaaaaa-1111-2222-3333-444444440001","message":{"role":"assistant","content":[{"type":"text","text":"Here is a phased approach."}]},"timestamp":"2026-01-15T10:00:30.000Z"}\n'
        )
        subagents = proj / "aaaaaaaa-1111-2222-3333-444444440001" / "subagents"
        subagents.mkdir(parents=True, exist_ok=True)
        (subagents / "agent-abc1234.jsonl").write_text(
            '{"type":"user","isSidechain":true,"cwd":"' + str(repo_path) + '","sessionId":"aaaaaaaa-1111-2222-3333-444444440001","agentId":"abc1234","message":{"role":"user","content":"Search for auth"},"timestamp":"2026-01-15T10:01:00.000Z"}\n'
            '{"type":"assistant","isSidechain":true,"cwd":"' + str(repo_path) + '","sessionId":"aaaaaaaa-1111-2222-3333-444444440001","agentId":"abc1234","message":{"role":"assistant","content":[{"type":"text","text":"Found 3 patterns."}]},"timestamp":"2026-01-15T10:01:15.000Z"}\n'
        )
        (proj / "bbbbbbbb-1111-2222-3333-444444440002.jsonl").write_text(
            '{"type":"user","cwd":"' + str(repo_path) + '","sessionId":"bbbbbbbb-1111-2222-3333-444444440002","message":{"role":"user","content":"Add health check"},"timestamp":"2026-01-15T11:00:00.000Z"}\n'
            '{"type":"assistant","cwd":"' + str(repo_path) + '","sessionId":"bbbbbbbb-1111-2222-3333-444444440002","message":{"role":"assistant","content":[{"type":"text","text":"I will add /health."}]},"timestamp":"2026-01-15T11:00:20.000Z"}\n'
        )

    def write_backend_api_project():
        api_path = repo_path / "api"
        proj = projects_dir / encoded_api
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "cccccccc-1111-2222-3333-444444440003.jsonl").write_text(
            '{"type":"user","cwd":"' + str(api_path) + '","sessionId":"cccccccc-1111-2222-3333-444444440003","message":{"role":"user","content":"Refactor API routes"},"timestamp":"2026-01-15T12:00:00.000Z"}\n'
            '{"type":"assistant","cwd":"' + str(api_path) + '","sessionId":"cccccccc-1111-2222-3333-444444440003","message":{"role":"assistant","content":[{"type":"text","text":"Extracting routes."}]},"timestamp":"2026-01-15T12:00:25.000Z"}\n'
        )

    def write_other_project():
        proj = projects_dir / encoded_other
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "dddddddd-1111-2222-3333-444444440004.jsonl").write_text(
            '{"type":"user","cwd":"/Users/alice/Code/other","sessionId":"dddddddd-1111-2222-3333-444444440004","message":{"role":"user","content":"Different repo"},"timestamp":"2026-01-15T13:00:00.000Z"}\n'
            '{"type":"assistant","cwd":"/Users/alice/Code/other","sessionId":"dddddddd-1111-2222-3333-444444440004","message":{"role":"assistant","content":[{"type":"text","text":"Done."}]},"timestamp":"2026-01-15T13:00:10.000Z"}\n'
        )

    write_backend_project()
    write_backend_api_project()
    write_other_project()
    return projects_dir


def test_claude_backup_writes_session_folders(tmp_path: Path) -> None:
    output_repo = tmp_path / "backup-repo"
    _init_git_repo(output_repo)
    repo_path = tmp_path / "Users" / "alice" / "Code" / "backend"
    projects_dir = _setup_claude_fixtures(tmp_path, repo_path)

    run = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "claude",
        "--input-path", str(projects_dir),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run.returncode == 0, run.stderr
    _assert_backup_counts(run.stdout, exported=4)

    history = output_repo / "history" / "alice" / "claude" / "macbook-pro"
    session_dirs = sorted(history.rglob("index.md"))
    assert len(session_dirs) >= 2
    session_with_subagent = next(
        (d.parent for d in session_dirs if (d.parent / "agent-abc1234.md").exists()),
        None,
    )
    assert session_with_subagent is not None
    assert (session_with_subagent / "index.md").exists()
    assert (session_with_subagent / "agent-abc1234.md").exists()


def test_claude_backup_is_idempotent(tmp_path: Path) -> None:
    output_repo = tmp_path / "backup-repo"
    _init_git_repo(output_repo)
    repo_path = tmp_path / "Users" / "alice" / "Code" / "backend"
    projects_dir = _setup_claude_fixtures(tmp_path, repo_path)

    run_one = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "claude",
        "--input-path", str(projects_dir),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run_one.returncode == 0, run_one.stderr
    _assert_backup_counts(run_one.stdout, exported=4)

    run_two = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "claude",
        "--input-path", str(projects_dir),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run_two.returncode == 0, run_two.stderr
    _assert_backup_counts(run_two.stdout, skipped=4)


def test_claude_sync_filters_to_repo_and_subfolders(tmp_path: Path) -> None:
    project_repo = tmp_path / "Users" / "alice" / "Code" / "backend"
    _init_git_repo(project_repo)
    projects_dir = _setup_claude_fixtures(tmp_path, project_repo)

    run = _run_cli([
        "sync",
        "--source-system", "claude",
        "--input-path", str(projects_dir),
        "--user", "alice",
        "--history-subpath", "history",
    ], cwd=project_repo)
    assert run.returncode == 0, run.stderr
    assert "exported=3" in run.stdout
    assert "discovered=3" in run.stdout

    history_root = project_repo / "history" / "alice" / "claude"
    session_dirs = list(history_root.rglob("index.md"))
    assert len(session_dirs) == 3


def test_claude_sync_always_uses_folder_structure(tmp_path: Path) -> None:
    project_repo = tmp_path / "Users" / "alice" / "Code" / "backend"
    _init_git_repo(project_repo)
    projects_dir = _setup_claude_fixtures(tmp_path, project_repo)

    run = _run_cli([
        "sync",
        "--source-system", "claude",
        "--input-path", str(projects_dir),
        "--user", "alice",
        "--history-subpath", "history",
    ], cwd=project_repo)
    assert run.returncode == 0, run.stderr

    history_root = project_repo / "history" / "alice" / "claude"
    md_files = list(history_root.rglob("*.md"))
    assert all(f.name in ("index.md", "agent-abc1234.md") for f in md_files)
    assert not any(f.suffix == ".md" and f.name != "index.md" and not f.name.startswith("agent-") for f in history_root.rglob("*"))
