from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_TMP = ROOT / "tests" / "fixtures" / "gemini_tmp"
FIXTURES_PROJECTS = ROOT / "tests" / "fixtures" / "gemini_projects.json"


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1"})
    return subprocess.run(
        [sys.executable, "-m", "convx_ai", *args],
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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rewrite_project_hash(session_file: Path, project_path: Path) -> None:
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    payload["projectHash"] = _sha256_text(str(project_path))
    session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _setup_gemini_fixtures(tmp_path: Path, repo_path: Path) -> Path:
    gemini_home = tmp_path / "gemini_home"
    tmp_root = gemini_home / "tmp"
    shutil.copytree(FIXTURES_TMP, tmp_root)
    shutil.copy(FIXTURES_PROJECTS, gemini_home / "projects.json")

    other_repo = tmp_path / "Users" / "alice" / "Code" / "other"
    other_repo.mkdir(parents=True, exist_ok=True)

    (tmp_root / "backend" / ".project_root").write_text(f"{repo_path}\n", encoding="utf-8")
    (tmp_root / "outside" / ".project_root").write_text(f"{other_repo}\n", encoding="utf-8")

    projects_payload = {
        "projects": {
            str(repo_path): "backend",
            str(repo_path / "api"): "backend-api",
            str(other_repo): "other",
        }
    }
    (gemini_home / "projects.json").write_text(
        json.dumps(projects_payload, indent=2),
        encoding="utf-8",
    )

    _rewrite_project_hash(
        tmp_root / "backend" / "chats" / "session-2026-03-02T10-00-11111111.json",
        repo_path,
    )
    _rewrite_project_hash(
        tmp_root / "hash-only" / "chats" / "session-2026-03-02T10-10-22222222.json",
        repo_path / "api",
    )
    _rewrite_project_hash(
        tmp_root / "outside" / "chats" / "session-2026-03-02T10-20-33333333.json",
        other_repo,
    )
    return gemini_home


def test_gemini_backup_writes_expected_structure_and_content(tmp_path: Path) -> None:
    output_repo = tmp_path / "backup-repo"
    _init_git_repo(output_repo)
    repo_path = tmp_path / "Users" / "alice" / "Code" / "backend"
    gemini_home = _setup_gemini_fixtures(tmp_path, repo_path)

    run_one = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "gemini",
        "--input-path", str(gemini_home),
        "--user", "alice",
        "--system-name", "macbook-pro",
        "--with-context",
        "--with-thinking",
    ])
    assert run_one.returncode == 0, run_one.stderr
    _assert_backup_counts(run_one.stdout, exported=3)

    target = output_repo / "history" / "alice" / "gemini" / "macbook-pro"
    markdown_files = sorted(target.rglob("*.md"))
    json_files = sorted(target.rglob(".*.json"))
    assert len(markdown_files) == 3
    assert len(json_files) == 3

    markdown_blob = "\n".join(path.read_text(encoding="utf-8") for path in markdown_files)
    assert "Please summarize the deployment plan." in markdown_blob
    assert "I will inspect the repo and summarize key changes." in markdown_blob
    assert "[tool_call] run_shell_command" in markdown_blob
    assert "[tool_result] run_shell_command status=success" in markdown_blob
    assert "[error] Request cancelled." in markdown_blob

    json_blob = "\n".join(path.read_text(encoding="utf-8") for path in json_files)
    assert '"source_system": "gemini"' in json_blob

    run_two = _run_cli([
        "backup",
        "--output-path", str(output_repo),
        "--source-system", "gemini",
        "--input-path", str(gemini_home),
        "--user", "alice",
        "--system-name", "macbook-pro",
    ])
    assert run_two.returncode == 0, run_two.stderr
    _assert_backup_counts(run_two.stdout, skipped=3)


def test_gemini_sync_filters_to_repo_and_uses_hash_fallback(tmp_path: Path) -> None:
    project_repo = tmp_path / "Users" / "alice" / "Code" / "backend"
    _init_git_repo(project_repo)
    gemini_home = _setup_gemini_fixtures(tmp_path, project_repo)

    run = _run_cli([
        "sync",
        "--source-system", "gemini",
        "--input-path", str(gemini_home),
        "--user", "alice",
        "--recursive",
        "--history-subpath", ".ai/history",
    ], cwd=project_repo)
    assert run.returncode == 0, run.stderr
    assert "discovered=3" in run.stdout
    assert "exported=2" in run.stdout
    assert "filtered=1" in run.stdout

    history_root = project_repo / ".ai" / "history" / "alice" / "gemini"
    markdown_files = sorted(history_root.rglob("*.md"))
    assert len(markdown_files) == 2
    content = "\n".join(path.read_text(encoding="utf-8") for path in markdown_files)
    assert "Refactor API routes into smaller modules." in content


def test_gemini_sync_from_subdirectory_is_recursive_by_default(tmp_path: Path) -> None:
    project_repo = tmp_path / "Users" / "alice" / "Code" / "backend"
    _init_git_repo(project_repo)
    nested = project_repo / "api"
    nested.mkdir(parents=True, exist_ok=True)
    gemini_home = _setup_gemini_fixtures(tmp_path, project_repo)

    run = _run_cli([
        "sync",
        "--source-system", "gemini",
        "--input-path", str(gemini_home),
        "--user", "alice",
    ], cwd=nested)
    assert run.returncode == 0, run.stderr
    assert "discovered=3" in run.stdout
    assert "exported=1" in run.stdout
    assert "filtered=2" in run.stdout

    history_root = project_repo / ".ai" / "history" / "alice" / "gemini"
    markdown_files = sorted(history_root.rglob("*.md"))
    assert len(markdown_files) == 1
