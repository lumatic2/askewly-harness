"""handoff_commit.sh 계약 테스트 (HO1 2026-07-27).

계약: HANDOFF.md 단독 커밋(다른 dirty/staged 비오염) · 실패는 경고+exit 0 ·
linked worktree 쓰기 거부 · --to-main 은 main HANDOFF.md dirty 면 보류.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "handoff_commit.sh"


def _find_bash() -> str | None:
    # Windows: system32 bash 는 WSL 이라 경로가 깨진다 — Git Bash 를 우선한다.
    for cand in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(cand).exists():
            return cand
    found = shutil.which("bash")
    if found and "system32" in found.lower():
        return None
    return found


BASH = _find_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def run_helper(repo: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        cwd=str(repo), input=stdin,
        capture_output=True, text=True, encoding="utf-8",
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "README.md").write_text("hi\n", encoding="utf-8")
    git(r, "add", "README.md")
    git(r, "commit", "-m", "init")
    return r


def test_commits_only_handoff_leaves_dirty_and_staged(repo: Path):
    (repo / "HANDOFF.md").write_text("## 이어서 할 일\n- x\n", encoding="utf-8")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")  # dirty tracked
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "staged.txt")  # 남의 staged 변경 시뮬

    proc = run_helper(repo)
    assert proc.returncode == 0, proc.stderr

    files = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files == ["HANDOFF.md"]
    assert "README.md" in git(repo, "diff", "--name-only")  # dirty 그대로
    assert "staged.txt" in git(repo, "diff", "--cached", "--name-only")  # staged 그대로, 미커밋


def test_no_remote_warns_exit0(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo)
    assert proc.returncode == 0
    assert "remote 없음" in proc.stdout
    assert git(repo, "log", "--format=%s", "-1").startswith("chore(handoff)")


def test_no_change_noop(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    run_helper(repo)
    before = git(repo, "rev-parse", "HEAD")
    proc = run_helper(repo)  # 변경 없음
    assert proc.returncode == 0
    assert "변경 없음" in proc.stdout
    assert git(repo, "rev-parse", "HEAD") == before


def test_missing_handoff_warns_exit0(repo: Path):
    proc = run_helper(repo)
    assert proc.returncode == 0
    assert "HANDOFF.md 없음" in proc.stdout


def test_not_a_repo_warns_exit0(tmp_path: Path):
    proc = run_helper(tmp_path)
    assert proc.returncode == 0
    assert "git 레포가 아님" in proc.stdout


def test_linked_worktree_refused(repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", str(wt), "-b", "feature")
    (wt / "HANDOFF.md").write_text("- wt note\n", encoding="utf-8")
    before = git(wt, "rev-parse", "HEAD")

    proc = run_helper(wt)
    assert proc.returncode == 0
    assert "worktree" in proc.stdout
    assert git(wt, "rev-parse", "HEAD") == before  # 커밋 안 됨


def test_to_main_writes_and_commits_in_main(repo: Path, tmp_path: Path):
    (repo / "HANDOFF.md").write_text("- old\n", encoding="utf-8")
    git(repo, "add", "HANDOFF.md")
    git(repo, "commit", "-m", "handoff init")
    wt = tmp_path / "wt2"
    git(repo, "worktree", "add", str(wt), "-b", "feature2")

    proc = run_helper(wt, "--to-main", stdin="- repo-level note\n")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "커밋 완료" in proc.stdout
    assert "repo-level note" in (repo / "HANDOFF.md").read_text(encoding="utf-8")
    files = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files == ["HANDOFF.md"]


def test_to_main_deferred_when_main_dirty(repo: Path, tmp_path: Path):
    (repo / "HANDOFF.md").write_text("- committed\n", encoding="utf-8")
    git(repo, "add", "HANDOFF.md")
    git(repo, "commit", "-m", "handoff init")
    (repo / "HANDOFF.md").write_text("- hand edit\n", encoding="utf-8")  # main dirty
    wt = tmp_path / "wt3"
    git(repo, "worktree", "add", str(wt), "-b", "feature3")
    before = git(repo, "rev-parse", "HEAD")

    proc = run_helper(wt, "--to-main", stdin="- overwrite attempt\n")
    assert proc.returncode == 0
    assert "보류" in proc.stdout
    assert (repo / "HANDOFF.md").read_text(encoding="utf-8") == "- hand edit\n"  # 불변
    assert git(repo, "rev-parse", "HEAD") == before
