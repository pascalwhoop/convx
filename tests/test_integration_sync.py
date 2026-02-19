from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "codex_sessions"


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "conversation_exporter", *args],
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)


def test_backup_writes_expected_structure_and_is_idempotent(tmp_path: Path) -> None:
    output_repo = tmp_path / "backup-repo"
    _init_git_repo(output_repo)

    run_one = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "codex",
        "--input-path", str(FIXTURES),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run_one.returncode == 0, run_one.stderr
    assert "exported=2" in run_one.stdout

    target = output_repo / "history" / "alice" / "codex" / "macbook-pro" / "Code"
    markdown_files = sorted(target.rglob("*.md"))
    json_files = sorted(target.rglob(".*.json"))
    assert len(markdown_files) == 2
    assert len(json_files) == 2

    run_two = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "codex",
        "--input-path", str(FIXTURES),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run_two.returncode == 0, run_two.stderr
    assert "skipped=2" in run_two.stdout
    assert len(sorted(target.rglob("*.md"))) == 2
    assert len(sorted(target.rglob(".*.json"))) == 2


def test_sync_filters_to_current_git_repository(tmp_path: Path) -> None:
    project_repo = tmp_path / "backend"
    _init_git_repo(project_repo)

    run = _run_cli([
        "sync",
        "--source-system", "codex",
        "--input-path", str(FIXTURES),
        "--user", "alice",
        "--system-name", "macbook-pro",
        "--history-subpath", ".ai/history",
    ], cwd=project_repo)
    assert run.returncode == 0, run.stderr
    assert "filtered=1" in run.stdout
    assert "exported=1" in run.stdout

    history_root = project_repo / ".ai" / "history" / "alice" / "codex"
    markdown_files = sorted(history_root.rglob("*.md"))
    assert len(markdown_files) == 1
