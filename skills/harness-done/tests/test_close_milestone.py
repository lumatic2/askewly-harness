"""close_milestone.py — report_close → ROADMAP complete → 계획서 archive 이동 → 포인터 수리를 한 번에."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

PROMOTED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROMOTED / "harness-done" / "bin"))

import close_milestone  # noqa: E402
import report_evidence  # noqa: E402

ROADMAP = """# ROADMAP

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 - first proof
- DoD: run passes
- Evidence: evidence/run.json
- Gap: none
- Plan: plans/2026-11-16-M1-x.md
- Status: [ ]

## Completed
"""

NOTE = """# 완료 — M1

## 1. 결과
됐다.

## 2. 이슈와 해결
없음.

## 3. 증거
- 검증: python -m pytest → 3 passed
- 실표면: none — 내부 스크립트
- 재현: python a.py
- 감사: none — 사용자 생략
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def make_repo(tmp_path: Path, *, suite: bool = True, ignore: str = "") -> tuple[Path, list[str]]:
    root = tmp_path / "repo"
    (root / "plans").mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".harness/\n" + ignore, encoding="utf-8")
    (root / "ROADMAP.md").write_text(ROADMAP, encoding="utf-8")
    (root / "plans" / "2026-11-16-M1-x.md").write_text("# plan\n- [x] **step-1 — a**\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "init")
    head = git(root, "rev-parse", "HEAD").strip()
    if suite:
        (root / ".harness").mkdir()
        (root / ".harness" / "suite-gate.json").write_text(
            json.dumps({"status": "pass", "head": head, "command": "pytest", "dirty": 0}), encoding="utf-8")
    note = root / "archive" / "reports" / "2026-11-16-M1-x.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE, encoding="utf-8")
    report_evidence.main(["--root", str(root), "--base", "HEAD", "--write", str(note)])
    args = ["--root", str(root), "--report", "archive/reports/2026-11-16-M1-x.md", "--task-id", "T1",
            "--milestone", "M1", "--summary", "첫 증명 완료", "--plan", "plans/2026-11-16-M1-x.md"]
    return root, args


def test_closes_moves_plan_and_is_rerunnable(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    assert close_milestone.main(args) == 0
    ledger = (root / ".harness" / "execution-ledger.jsonl").read_text(encoding="utf-8")
    assert '"task_completed"' in ledger
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert 'id="M1" status="completed"' in roadmap
    assert (root / "archive" / "plans" / "2026-11-16-M1-x.md").exists()
    assert not (root / "plans" / "2026-11-16-M1-x.md").exists()
    assert "compact: ROADMAP" in capsys.readouterr().out  # 150줄 이하면 건너뛴다

    # 다시 돌려도 이미 끝난 단계는 건너뛰고 원장에 완료가 두 번 쌓이지 않는다
    assert close_milestone.main(args) == 0
    again = (root / ".harness" / "execution-ledger.jsonl").read_text(encoding="utf-8")
    assert again.count('"task_completed"') == 1
    assert "이미 닫혔다" in capsys.readouterr().out


def test_stops_at_failed_step_without_touching_roadmap(tmp_path, capsys):
    root, args = make_repo(tmp_path, suite=False)
    assert close_milestone.main(args) == 1
    assert "실패 — report_close" in capsys.readouterr().err
    assert 'id="M1" status="active"' in (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert (root / "plans" / "2026-11-16-M1-x.md").exists()


def printed_commands(out: str) -> dict[str, list[str]]:
    """스크립트가 끝에서 찍은 `git add`·`git commit` 줄을 셸 규칙대로 쪼갠다 — 그대로 실행되는지 보려고."""
    cmds: dict[str, list[str]] = {}
    for ln in out.splitlines():
        if ln.startswith("git add ") or ln.startswith("git commit "):
            words = shlex.split(ln)
            cmds[words[1]] = words
    return cmds


def run_printed(root: Path, words: list[str]) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *words[1:]],
                   check=True, capture_output=True, text=True)


def test_prints_runnable_add_and_commit_without_moved_or_stale_paths(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    assert close_milestone.main(args) == 0
    out = capsys.readouterr().out
    cmds = printed_commands(out)
    # 이미 `git mv` 로 스테이징된 이동은 add 목록에 없고, 이미 없는 옛 plans/ 경로도 없다
    assert cmds["add"] == ["git", "add", "--", "ROADMAP.md", "archive/reports/2026-11-16-M1-x.md"]
    assert "이동은 이미 스테이징됨: plans/2026-11-16-M1-x.md" in out
    assert "archive/plans/2026-11-16-M1-x.md" in out

    # 다시 돌려도(끝난 단계는 건너뜀) 같은 목록이 나온다
    assert close_milestone.main(args) == 0
    assert printed_commands(capsys.readouterr().out)["add"] == cmds["add"]

    # 찍힌 명령을 그대로 실행하면 add 가 통째로 실패하지 않고 마감 커밋에 이동·노트·ROADMAP 이 다 담긴다
    run_printed(root, cmds["add"])
    run_printed(root, cmds["commit"])
    assert git(root, "status", "--porcelain").strip() == ""
    shown = git(root, "show", "--name-status", "--format=", "HEAD")
    assert "ROADMAP.md" in shown and "archive/reports/2026-11-16-M1-x.md" in shown
    assert "archive/plans/2026-11-16-M1-x.md" in shown and "plans/2026-11-16-M1-x.md" in shown


def test_gitignored_paths_are_not_in_add_list_and_are_announced(tmp_path, capsys):
    # 추적 안 된 계획서를 gitignore 된 `archive/plans/` 로 옮기면 그 경로는 add 할 수 없다 (실제 add 통째 실패 사례)
    root, args = make_repo(tmp_path, ignore="archive/plans/\n")
    (root / "plans" / "2026-11-16-M1-y.md").write_text("# plan y\n", encoding="utf-8")
    args = [*args[:-1], "plans/2026-11-16-M1-y.md"]
    assert close_milestone.main(args) == 0
    out = capsys.readouterr().out
    cmds = printed_commands(out)
    assert cmds["add"] == ["git", "add", "--", "ROADMAP.md", "archive/reports/2026-11-16-M1-x.md"]
    assert "archive/plans/2026-11-16-M1-y.md" not in " ".join(cmds["commit"])
    assert "gitignore 대상이라 추적할 수 없어" in out and "archive/plans/2026-11-16-M1-y.md" in out
    run_printed(root, cmds["add"])  # ignored 경로가 없으니 add 가 실패하지 않는다
    run_printed(root, cmds["commit"])


def test_untracked_plan_moved_by_plain_move_is_added(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    (root / "plans" / "2026-11-16-M1-y.md").write_text("# plan y\n", encoding="utf-8")  # 추적 안 된 계획서
    args = [*args[:-1], "plans/2026-11-16-M1-y.md"]
    assert close_milestone.main(args) == 0
    cmds = printed_commands(capsys.readouterr().out)
    assert cmds["add"] == ["git", "add", "--", "ROADMAP.md", "archive/plans/2026-11-16-M1-y.md",
                           "archive/reports/2026-11-16-M1-x.md"]
    assert "plans/2026-11-16-M1-y.md" not in cmds["add"]


def add_branch_deliverable(root: Path) -> None:
    d = root / ".harness" / "fanout"
    d.mkdir(parents=True, exist_ok=True)
    (d / "branch.json").write_text(json.dumps({
        "main_work_id": "W1", "main_root": str(root.parent / "main"), "milestone_id": "M1", "branch_id": "b1",
        "title": "t", "dod": "d", "owns": ["a.py"], "base_branch": "master"}), encoding="utf-8")


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for sub in ("plans", "archive/plans") if (root / sub).exists()
            for p in (root / sub).rglob("*") if p.is_file()} | {"ROADMAP.md": (root / "ROADMAP.md").read_bytes()}


def test_branch_close_skips_roadmap(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    add_branch_deliverable(root)
    before = tree_bytes(root)
    assert close_milestone.main([*args, "--branch"]) == 0
    assert tree_bytes(root) == before  # ROADMAP.md·plans/ 바이트 그대로, 계획서 이동 없음
    ledger = (root / ".harness" / "execution-ledger.jsonl").read_text(encoding="utf-8")
    assert '"task_completed"' in ledger
    out = capsys.readouterr().out
    assert "fanout.py" in out and " ready " in out and "--note" in out and "--root" in out
    assert "git commit" not in out


def test_branch_flag_refused_outside_fanout_worktree(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    assert close_milestone.main([*args, "--branch"]) != 0
    assert not (root / ".harness" / "execution-ledger.jsonl").exists()
    assert 'id="M1" status="active"' in (root / "ROADMAP.md").read_text(encoding="utf-8")


def test_full_close_refused_inside_fanout_worktree(tmp_path, capsys):
    root, args = make_repo(tmp_path)
    add_branch_deliverable(root)
    assert close_milestone.main(args) != 0
    assert not (root / ".harness" / "execution-ledger.jsonl").exists()
    assert 'id="M1" status="active"' in (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert (root / "plans" / "2026-11-16-M1-x.md").exists()


def test_pending_milestone_needs_force_roadmap(tmp_path, capsys):
    """계획 승인 없이 pending 으로 남은 milestone — 기본은 거부, --force-roadmap 이면 닫는다(2026-11-19 M27)."""
    root, args = make_repo(tmp_path)
    text = (root / "ROADMAP.md").read_text(encoding="utf-8")
    (root / "ROADMAP.md").write_text(text.replace('status="active"', 'status="pending"'), encoding="utf-8")
    git(root, "commit", "-qam", "pending")
    head = git(root, "rev-parse", "HEAD").strip()
    (root / ".harness" / "suite-gate.json").write_text(
        json.dumps({"status": "pass", "head": head, "command": "pytest", "dirty": 0}), encoding="utf-8")
    note = root / "archive" / "reports" / "2026-11-16-M1-x.md"
    report_evidence.main(["--root", str(root), "--base", "HEAD", "--write", str(note)])
    assert close_milestone.main(args) == 1
    assert "roadmap complete" in capsys.readouterr().out
    assert 'status="pending"' in (root / "ROADMAP.md").read_text(encoding="utf-8")
    assert close_milestone.main(args + ["--force-roadmap"]) == 0
    assert 'id="M1" status="completed"' in (root / "ROADMAP.md").read_text(encoding="utf-8")
