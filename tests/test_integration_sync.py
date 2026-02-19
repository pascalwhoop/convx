from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "codex_sessions"
FIXTURES_REDACT = ROOT / "tests" / "fixtures" / "codex_sessions_redact"


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
    _assert_backup_counts(run_one.stdout, exported=2)

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
    _assert_backup_counts(run_two.stdout, skipped=2)
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


def test_secrets_redacted_in_output(tmp_path: Path) -> None:
    output_repo = tmp_path / "backup-repo"
    _init_git_repo(output_repo)
    secret_literal = "sk-proj-redact-test-abc123xyz"

    run = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "codex",
        "--input-path", str(FIXTURES_REDACT),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run.returncode == 0, run.stderr
    _assert_backup_counts(run.stdout, exported=1)

    for md_path in (output_repo / "history").rglob("*.md"):
        content = md_path.read_text(encoding="utf-8")
        assert secret_literal not in content, f"Secret found in {md_path}"
