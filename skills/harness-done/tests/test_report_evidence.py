"""report_evidence.py(§3 자동 블록 생성)와 report_close.py(블록 HEAD 대조)가 함께 도는지 본다."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROMOTED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROMOTED / "harness-done" / "bin"))
sys.path.insert(0, str(PROMOTED / "harness-run" / "scripts"))

import report_close  # noqa: E402
import report_evidence  # noqa: E402

NOTE = """# 완료

## 1. 결과
됐다.

## 2. 이슈와 해결
없음.

## 3. 증거
- 실표면: none — 내부 스크립트
- 재현: python a.py
- 감사: none — 스폰 조건 미해당
"""

PLAN = """# 계획

- [x] **step-1 — 첫째**
  - Artifact: a.py
  - Files: `a.py`, `tests/test_a.py::test_x`
- [x] **step-2 — 둘째**
  - Files: missing.py · docs/b.md
- [ ] **step-3 — 아직**
  - Files: `later.py`
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def commit(root: Path, name: str, body: str = "x") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-qm", name)


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".harness/\n", encoding="utf-8")
    commit(root, ".gitignore", ".harness/\n")
    base = git(root, "rev-parse", "HEAD").strip()
    commit(root, "a.py")
    commit(root, "tests/test_a.py")
    commit(root, "changesets/20261116-x/README.md")
    return root, base


def suite_pass(root: Path) -> None:
    head = git(root, "rev-parse", "HEAD").strip()
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness" / "suite-gate.json").write_text(json.dumps(
        {"status": "pass", "head": head, "command": "pytest", "elapsed_seconds": 3.2, "dirty": 0}), encoding="utf-8")


def test_block_states_head_range_count_suite_and_tracking(tmp_path):
    root, base = make_repo(tmp_path)
    (root / "plan.md").write_text(PLAN, encoding="utf-8")
    git(root, "add", "plan.md")
    git(root, "commit", "-qm", "plan")
    suite_pass(root)
    block, warnings = report_evidence.build(root, base, root / "plan.md", ["changesets/20261116-x"], None)
    head = git(root, "rev-parse", "HEAD").strip()
    assert f"- 기준 HEAD: `{head[:9]}`" in block
    assert "커밋 4개" in block
    assert "트리: 깨끗" in block
    assert "통과 — `pytest`" in block
    assert "`changesets/20261116-x` (git 추적)" in block
    # 완료 step 2개, Files 4개(a.py · tests/test_a.py · missing.py · docs/b.md), 미완 step 은 안 본다
    assert "완료 step 2개의 Files 4개 중 git 추적 2개" in block
    assert "이 레포에 없음 2개" in block and "`missing.py`" in block and "later.py" not in block
    assert warnings == []  # 없는 파일은 교차 레포일 수 있어 안내만 한다

    (root / "docs").mkdir()
    (root / "docs" / "b.md").write_text("b", encoding="utf-8")
    block, warnings = report_evidence.build(root, base, root / "plan.md", [], None)
    assert "있는데 추적 안 됨 1개 — `docs/b.md`" in block
    assert "미커밋 변경" in warnings and "산출물 추적" in warnings


def test_dirty_tree_and_stale_suite_are_warned(tmp_path):
    root, base = make_repo(tmp_path)
    suite_pass(root)
    commit(root, "late.py")
    (root / "a.py").write_text("changed", encoding="utf-8")
    block, warnings = report_evidence.build(root, base, None, [], None)
    assert "미커밋 1개 (`a.py`)" in block
    assert "다른 커밋의 기록" in block
    assert warnings == ["미커밋 변경", "스위트"]


def test_write_inserts_then_replaces_block_and_ignores_note_itself(tmp_path):
    root, base = make_repo(tmp_path)
    suite_pass(root)
    note = root / "note.md"
    note.write_text(NOTE, encoding="utf-8")
    assert report_evidence.main(["--root", str(root), "--base", base, "--write", str(note)]) == 0
    first = note.read_text(encoding="utf-8")
    assert first.index("## 3. 증거") < first.index(report_evidence.START) < first.index("- 실표면:")
    assert "트리: 깨끗" in first  # 아직 커밋 안 된 노트 자신은 미커밋으로 세지 않는다

    commit(root, "late.py")
    suite_pass(root)
    assert report_evidence.main(["--root", str(root), "--base", base, "--write", str(note)]) == 0
    second = note.read_text(encoding="utf-8")
    assert second.count(report_evidence.START) == 1
    assert "커밋 4개" in second and "커밋 3개" not in second


def test_close_refuses_missing_then_stale_block_and_accepts_fresh(tmp_path, capsys):
    root, base = make_repo(tmp_path)
    suite_pass(root)
    note = root / "note.md"
    note.write_text(NOTE, encoding="utf-8")
    args = [str(note), "--task-id", "T1", "--root", str(root)]

    assert report_close.main(args) == 1
    assert "자동 증거 블록이 없다" in capsys.readouterr().err

    report_evidence.main(["--root", str(root), "--base", base, "--write", str(note)])
    commit(root, "late.py")
    suite_pass(root)
    capsys.readouterr()
    assert report_close.main(args) == 1
    assert "다른 커밋 기준" in capsys.readouterr().err

    report_evidence.main(["--root", str(root), "--base", base, "--write", str(note)])
    assert report_close.main(args) == 0


def test_unknown_base_is_usage_error(tmp_path):
    root, _ = make_repo(tmp_path)
    assert report_evidence.main(["--root", str(root), "--base", "nope123"]) == 2


def make_repo_harness_visible(tmp_path: Path) -> tuple[Path, str]:
    """`.harness/` 가 gitignore 되지 않은 레포 — 하네스 상태 파일이 미추적으로 보이는 실제 사례."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    commit(root, "README.md")
    base = git(root, "rev-parse", "HEAD").strip()
    commit(root, "a.py")
    return root, base


def test_note_in_untracked_new_folder_is_not_counted_as_dirty(tmp_path):
    # `git status --porcelain` 은 추적 안 된 새 폴더를 `archive/` 한 줄로 접는다 — 노트 자신이 빠지지 않던 사례
    root, base = make_repo(tmp_path)
    suite_pass(root)
    note = root / "archive" / "reports" / "n.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE, encoding="utf-8")
    assert report_evidence.main(["--root", str(root), "--base", base, "--write", str(note)]) == 0
    assert "트리: 깨끗" in note.read_text(encoding="utf-8")

    # 같은 새 폴더에 노트 말고 진짜 미커밋 파일이 있으면 그 파일만 센다
    (root / "archive" / "reports" / "other.md").write_text("o", encoding="utf-8")
    block, warnings = report_evidence.build(root, base, None, [], note)
    assert "미커밋 1개 (`archive/reports/other.md`)" in block
    assert "미커밋 변경" in warnings


def test_harness_state_paths_are_not_dirty_but_real_changes_still_are(tmp_path):
    root, base = make_repo_harness_visible(tmp_path)
    suite_pass(root)  # .harness/suite-gate.json (미추적)
    (root / ".harness" / "work.json").write_text("{}", encoding="utf-8")
    (root / ".harness" / "handoff").mkdir()
    (root / ".harness" / "handoff" / "h.md").write_text("h", encoding="utf-8")
    block, warnings = report_evidence.build(root, base, None, [], None)
    assert "트리: 깨끗" in block
    assert "미커밋 변경" not in warnings
    assert report_evidence.main(["--root", str(root), "--base", base]) == 0

    (root / "a.py").write_text("changed", encoding="utf-8")
    block, warnings = report_evidence.build(root, base, None, [], None)
    assert "미커밋 1개 (`a.py`)" in block and ".harness" not in block.split("스위트 기록")[0]
    assert "미커밋 변경" in warnings
    assert report_evidence.main(["--root", str(root), "--base", base]) == 1


def test_gitignored_files_entries_are_info_only_real_untracked_still_warns(tmp_path, capsys):
    root, base = make_repo(tmp_path)
    commit(root, ".gitignore", ".harness/\nCLAUDE.local.md\ntmp/\n")
    suite_pass(root)
    (root / "CLAUDE.local.md").write_text("x", encoding="utf-8")
    (root / "tmp" / "m1").mkdir(parents=True)
    (root / "tmp" / "m1" / "index.html").write_text("x", encoding="utf-8")
    plan = root / "plan.md"
    plan.write_text("# 계획\n\n- [x] **step-1 — 첫째**\n"
                    "  - Files: `a.py`, `CLAUDE.local.md`, `tmp/m1/index.html`\n", encoding="utf-8")
    commit(root, "plan.md", plan.read_text(encoding="utf-8"))
    suite_pass(root)
    block, warnings = report_evidence.build(root, base, plan, [], None)
    assert "Files 3개 중 git 추적 1개" in block
    assert "gitignore 대상 2개" in block and "`CLAUDE.local.md`" in block
    assert "있는데 추적 안 됨" not in block
    assert "산출물 추적" not in warnings
    assert report_evidence.main(["--root", str(root), "--base", base, "--plan", str(plan)]) == 0

    # 진짜 미추적 산출물은 그대로 경고 + exit 1
    plan.write_text(plan.read_text(encoding="utf-8").rstrip("\n") + ", `docs/b.md`\n", encoding="utf-8")
    commit(root, "plan.md", plan.read_text(encoding="utf-8"))
    suite_pass(root)
    (root / "docs").mkdir()
    (root / "docs" / "b.md").write_text("b", encoding="utf-8")
    capsys.readouterr()
    assert report_evidence.main(["--root", str(root), "--base", base, "--plan", str(plan)]) == 1
    out = capsys.readouterr()
    assert "있는데 추적 안 됨 1개 — `docs/b.md`" in out.out
    assert "gitignore 대상 2개" in out.out
    assert "산출물 추적" in out.err


def test_suite_line_passes_after_record_only_commit(tmp_path):
    root, base = make_repo(tmp_path)
    suite_pass(root)
    commit(root, "plans/p.md")
    commit(root, "archive/reports/n.md")
    head = git(root, "rev-parse", "HEAD").strip()
    text, ok = report_evidence.suite_line(root, head)
    assert ok is True
    assert text.startswith("통과 — `pytest`") and "기록 커밋 뒤 기록 파일 2개만 변경" in text
    block, warnings = report_evidence.build(root, base, None, [], None)
    assert "스위트" not in warnings and "다른 커밋" not in block


def test_suite_line_flags_source_commit(tmp_path):
    root, base = make_repo(tmp_path)
    suite_pass(root)
    commit(root, "plans/p.md")
    commit(root, "src/late.py")
    head = git(root, "rev-parse", "HEAD").strip()
    text, ok = report_evidence.suite_line(root, head)
    assert ok is False
    assert text.startswith("다른 커밋의 기록(") and "기록 커밋 뒤 기록 파일 밖이 바뀌었다: src/late.py" in text
    assert text.endswith("다시 돌린다")


def test_suite_line_reports_running_record(tmp_path):
    """실행 중이거나 중단된 기록은 「실패 exit None」이 아니라 실행 중으로 읽힌다."""
    root, base = make_repo(tmp_path)
    suite_pass(root)
    path = root / ".harness" / "suite-gate.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec.update(status="running", exit_code=None)
    path.write_text(json.dumps(rec), encoding="utf-8")
    head = git(root, "rev-parse", "HEAD").strip()
    text, ok = report_evidence.suite_line(root, head)
    assert ok is False
    assert "실행 중" in text and "exit None" not in text
