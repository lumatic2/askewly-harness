"""handoff_commit.sh 계약 테스트 (HO1 2026-07-27).

계약: HANDOFF.md 단독 커밋(다른 dirty/staged 비오염) · 실패는 경고+exit 0 ·
linked worktree 는 main 체크아웃 HANDOFF.md 를 커밋(2026-09-29) ·
<git-dir>/HANDOFF_COMMIT_MSG 가 있으면 커밋 본문에 붙이고 성공 시 지운다 · 커밋 거부 시 끝 40줄을 stderr 로 보이고 파일은 남긴다 ·
--to-main 은 은퇴(2026-11-07 M25) — 알 수 없는 인자 경고만 낸다.
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


def test_linked_worktree_commits_in_main(repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", str(wt), "-b", "feature")
    (repo / "HANDOFF.md").write_text("- merged block from wt\n", encoding="utf-8")
    before_wt = git(wt, "rev-parse", "HEAD")
    before_main = git(repo, "rev-parse", "HEAD")

    proc = run_helper(wt)
    assert proc.returncode == 0, proc.stdout
    assert "main 체크아웃" in proc.stdout and "커밋 완료" in proc.stdout
    assert git(wt, "rev-parse", "HEAD") == before_wt          # 워크트리 브랜치는 그대로
    assert git(repo, "rev-parse", "HEAD") != before_main      # main 에 커밋됨


def test_no_push_flag_skips_push(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo, "--no-push")
    assert proc.returncode == 0
    assert "커밋 완료" in proc.stdout and "--no-push" in proc.stdout


def test_commit_message_carries_completion_evidence(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    msg = repo / ".git" / "HANDOFF_COMMIT_MSG"
    msg.write_text("완료: X (b) — abc123\n", encoding="utf-8")
    proc = run_helper(repo)
    assert proc.returncode == 0, proc.stdout
    assert git(repo, "log", "-1", "--format=%s").startswith("chore(handoff): 세션 핸드오프 갱신")
    assert "완료: X (b) — abc123" in git(repo, "log", "-1", "--format=%b").splitlines()
    assert not msg.exists()


def test_commit_without_message_file_has_title_only(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo)
    assert proc.returncode == 0, proc.stdout
    assert git(repo, "log", "-1", "--format=%b") == ""


def test_hook_rejection_shows_reason(repo: Path):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text('#!/bin/sh\necho "REASON-LINE-XYZ" >&2\nexit 1\n', encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    msg = repo / ".git" / "HANDOFF_COMMIT_MSG"
    msg.write_text("완료: Y — def456\n", encoding="utf-8")
    before = git(repo, "rev-parse", "HEAD")
    proc = run_helper(repo)
    assert proc.returncode == 0
    assert "[handoff]   REASON-LINE-XYZ" in proc.stderr
    assert "커밋 실패" in proc.stdout
    assert git(repo, "rev-parse", "HEAD") == before
    assert msg.exists()


def test_to_main_flag_is_gone(repo: Path, tmp_path: Path):
    (repo / "HANDOFF.md").write_text("- old\n", encoding="utf-8")
    git(repo, "add", "HANDOFF.md")
    git(repo, "commit", "-m", "handoff init")
    wt = tmp_path / "wt_gone"
    git(repo, "worktree", "add", str(wt), "-b", "feature_gone")
    proc = run_helper(wt, "--to-main", stdin="- repo-level note\n")
    assert proc.returncode == 0
    assert "알 수 없는 인자: --to-main" in proc.stdout
    text = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    assert "워크트리에서 온 메모" not in text
    assert "repo-level note" not in text


@pytest.fixture()
def pushed_repo(repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "-u", "origin", "main")
    return repo, remote


def test_push_held_when_foreign_commit_ahead(pushed_repo):
    # 2026-11-05 실측: 핸드오프 push 가 다른 세션의 리뷰 전 커밋까지 올렸다
    repo, remote = pushed_repo
    (repo / "other.txt").write_text("o\n", encoding="utf-8")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-q", "-m", "feat: 다른 세션 작업")
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo)
    assert proc.returncode == 0
    assert "push 보류" in proc.stdout and "다른 세션 작업" in proc.stdout
    assert git(repo, "rev-list", "--count", "@{u}..HEAD") == "2"
    # 이 세션 것임을 확인했으면 --push-all — HANDOFF 변경이 없어도 push 단계로 간다
    proc = run_helper(repo, "--push-all")
    assert "push 완료" in proc.stdout, proc.stdout
    assert git(repo, "rev-list", "--count", "@{u}..HEAD") == "0"


def test_push_goes_when_only_handoff_and_hygiene_ahead(pushed_repo):
    repo, _ = pushed_repo
    (repo / "README.md").write_text("fixed\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "chore(hygiene): 경로 교정")
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo)
    assert "push 완료" in proc.stdout, proc.stdout
    assert git(repo, "rev-list", "--count", "@{u}..HEAD") == "0"


def test_commit_label_is_ascii_and_never_raw_uname(repo: Path):
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    run_helper(repo)
    subject = git(repo, "log", "-1", "--format=%s")
    assert "MINGW" not in subject and "MSYS" not in subject


def test_with_path_commits_backlog_alongside(repo: Path):
    (repo / "docs").mkdir()
    (repo / "docs" / "BACKLOG.md").write_text("# BACKLOG\n", encoding="utf-8")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")
    (repo / "HANDOFF.md").write_text("- x\n", encoding="utf-8")
    proc = run_helper(repo, "--with", "docs/BACKLOG.md")
    assert proc.returncode == 0, proc.stderr
    files = sorted(git(repo, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert files == ["HANDOFF.md", "docs/BACKLOG.md"]
    assert "README.md" in git(repo, "diff", "--name-only")


def test_with_file_from_merger_is_committed_and_removed(repo: Path):
    (repo / "docs").mkdir()
    (repo / "docs" / "BACKLOG.md").write_text("# BACKLOG\n- x\n", encoding="utf-8")
    (repo / "HANDOFF.md").write_text("- y\n", encoding="utf-8")
    (repo / ".git" / "HANDOFF_WITH").write_text("docs/BACKLOG.md\n", encoding="utf-8")
    proc = run_helper(repo)
    assert proc.returncode == 0, proc.stderr
    files = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(files) == ["HANDOFF.md", "docs/BACKLOG.md"]
    assert not (repo / ".git" / "HANDOFF_WITH").exists()


def test_hook_rejection_reason_beyond_five_lines_goes_to_stderr(repo: Path):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text('#!/bin/sh\necho "GATE: reason"\nfor i in 1 2 3 4 5 6 7 8; do echo "tail-$i"; done\nexit 1\n',
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    (repo / "HANDOFF.md").write_text("# HANDOFF\n- 새 줄\n", encoding="utf-8")
    r = run_helper(repo, "--no-push")
    assert r.returncode == 0
    assert "GATE: reason" in r.stderr and "tail-8" in r.stderr
    assert "STATUS_ROADMAP_ALLOW_NOOP" not in r.stdout + r.stderr
