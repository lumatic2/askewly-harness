"""suite_gate.py(실행·기록)와 report_close.py(대조)가 함께 닫기를 막는지 끝까지 돌려 본다."""

from __future__ import annotations

import json

import pytest
import subprocess
import sys
import time
from pathlib import Path

PROMOTED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROMOTED / "harness-done" / "bin"))
sys.path.insert(0, str(PROMOTED / "harness-run" / "scripts"))

import report_close  # noqa: E402
import report_evidence  # noqa: E402
import suite_gate  # noqa: E402

PASS = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAIL = f'"{sys.executable}" -c "raise SystemExit(3)"'

NOTE = """# 완료

## 1. 결과
됐다.

## 2. 이슈와 해결
없음.

## 3. 증거
- 실표면: none — 내부 스크립트
- 재현: python x.py
- 감사: none — 스폰 조건 미해당
{extra}"""


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True, capture_output=True,
    )


def make_repo(tmp_path: Path, extra: str = "") -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "a.txt").write_text("a", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "first")
    note = root / "note.md"
    note.write_text(NOTE.format(extra=extra), encoding="utf-8")
    return root, note


def close(root: Path, note: Path) -> int:
    # 2026-11-16: 노트 §3 자동 증거 블록이 있어야 닫힌다 — 실제 흐름처럼 닫기 직전에 생성한다
    report_evidence.main(["--root", str(root), "--base", "HEAD", "--write", str(note)])
    return report_close.main([str(note), "--task-id", "T1", "--root", str(root)])


def record(root: Path) -> dict:
    return json.loads((root / ".harness" / "suite-gate.json").read_text(encoding="utf-8"))


def test_close_refused_without_record(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert close(root, note) == 1
    err = capsys.readouterr().err
    assert "스위트 실행 기록이 없다" in err
    assert "suite_gate.py" in err  # 무엇을 돌릴지 메시지가 알려 줘야 한다


def test_passing_suite_lets_close_through_and_lands_in_ledger(tmp_path):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    assert record(root)["status"] == "pass"
    assert close(root, note) == 0
    ledger = (root / ".harness" / "execution-ledger.jsonl").read_text(encoding="utf-8")
    assert "스위트 통과" in ledger


def test_failing_suite_blocks_close(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", FAIL]) == 1
    rec = record(root)
    assert rec["status"] == "fail"
    assert rec["exit_code"] == 3
    capsys.readouterr()
    assert close(root, note) == 1
    assert "실패 상태" in capsys.readouterr().err


def test_commit_after_run_makes_record_stale(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    (root / "a.txt").write_text("b", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "second")
    capsys.readouterr()
    assert close(root, note) == 1
    assert "다른 커밋" in capsys.readouterr().err


def test_waive_needs_reason_and_note_line(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--waive", "  "]) == 2
    assert suite_gate.main(["--root", str(root), "--waive", "플레이키 — 남의 PR 에서도 실패"]) == 0
    assert record(root)["status"] == "waived"
    capsys.readouterr()
    assert close(root, note) == 1
    assert "waived" in capsys.readouterr().err

    note.write_text(NOTE.format(extra="- 스위트: waived — 플레이키\n"), encoding="utf-8")
    assert close(root, note) == 0


def test_repo_without_tests_records_none_and_closes(tmp_path):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root)]) == 0
    assert record(root)["status"] == "none"
    assert close(root, note) == 0


def test_non_git_root_is_not_held_hostage(tmp_path, capsys):
    root = tmp_path / "plain"
    root.mkdir()
    note = root / "note.md"
    note.write_text(NOTE.format(extra=""), encoding="utf-8")
    assert close(root, note) == 0
    assert "대조하지 않았다" in capsys.readouterr().err


def test_broken_record_counts_as_missing(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    (root / ".harness").mkdir()
    (root / ".harness" / "suite-gate.json").write_text("{깨짐", encoding="utf-8")
    assert close(root, note) == 1
    assert "기록이 없다" in capsys.readouterr().err


def test_timeout_records_fail(tmp_path):
    root, _ = make_repo(tmp_path)
    slow = f'"{sys.executable}" -c "import time; time.sleep(60)"'
    assert suite_gate.main(["--root", str(root), "--command", slow, "--timeout", "1"]) == 1
    rec = record(root)
    assert rec["status"] == "fail"
    assert rec["exit_code"] is None
    assert "시간 초과(1초)" in rec["reason"]


def test_pytest_collecting_nothing_is_none_not_fail(tmp_path):
    root, _ = make_repo(tmp_path)
    (root / "tests").mkdir()
    code = suite_gate.main(["--root", str(root), "--command", f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests'])
    assert code == 0
    assert record(root)["status"] == "none"


def test_detection(tmp_path):
    assert suite_gate.detect_commands(tmp_path) == []

    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}', encoding="utf-8")
    assert suite_gate.detect_commands(tmp_path) == []

    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    assert suite_gate.detect_commands(tmp_path) == ["npm test"]

    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    commands = suite_gate.detect_commands(tmp_path)
    assert len(commands) == 2
    assert "-m pytest -q" in commands[0]
    assert commands[1] == "npm test"


def test_pyproject_without_pytest_section_is_not_detected(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert suite_gate.detect_commands(tmp_path) == []


def test_failure_prints_tail_80_and_keeps_full_log(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    noisy = f'"{sys.executable}" -c "[print(\'line\' + str(i)) for i in range(200)]; raise SystemExit(3)"'
    assert suite_gate.main(["--root", str(root), "--command", noisy]) == 1
    out = capsys.readouterr().out
    assert "line199" in out and "line120" in out
    assert "line119" not in out  # 끝 80줄만
    log = root / ".harness" / "suite-gate.log"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "line0\n" in text and "line199" in text
    assert str(log) in out
    assert record(root)["log"] == str(log)


def test_timeout_reason_and_partial_log(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    slow = f'"{sys.executable}" -u -c "import time; print(\'partial-out\', flush=True); time.sleep(60)"'
    assert suite_gate.main(["--root", str(root), "--command", slow, "--timeout", "2"]) == 1
    out = capsys.readouterr().out
    assert "시간 초과(2초)" in out
    assert "partial-out" in (root / ".harness" / "suite-gate.log").read_text(encoding="utf-8")


def test_default_timeout_is_3600_and_env_overrides(monkeypatch):
    assert suite_gate.DEFAULT_TIMEOUT == 3600
    monkeypatch.setenv("SUITE_GATE_TIMEOUT", "77")
    assert suite_gate.default_timeout() == 77


def test_success_log_is_live_and_receipt_has_timing(tmp_path):
    root, _ = make_repo(tmp_path)
    command = f'"{sys.executable}" -u -c "from pathlib import Path; print(\'live-marker\', flush=True); assert \'live-marker\' in Path(\'.harness/suite-gate.log\').read_text()"'
    assert suite_gate.main(["--root", str(root), "--command", command]) == 0
    rec = record(root)
    assert "live-marker" in (root / ".harness" / "suite-gate.log").read_text()
    assert rec["log"] == str(root / ".harness" / "suite-gate.log")
    assert rec["started_at"] and rec["completed_at"]
    assert rec["elapsed_seconds"] >= 0
    assert rec["start_head"] == rec["head"]


def test_multiple_commands_preserve_all_output(tmp_path, monkeypatch):
    root, _ = make_repo(tmp_path)
    monkeypatch.setattr(suite_gate, "detect_commands", lambda root: [
        f'"{sys.executable}" -c "print(\'first-marker\')"',
        f'"{sys.executable}" -c "print(\'second-marker\')"',
    ])
    assert suite_gate.main(["--root", str(root)]) == 0
    text = (root / ".harness" / "suite-gate.log").read_text()
    assert "first-marker" in text and "second-marker" in text


def _commit_during(rel: str) -> str:
    """스위트 명령 자체가 실행 중에 파일 하나를 커밋한다 — 「도는 동안 다른 커밋」 재현."""
    code = (
        "import pathlib,subprocess;"
        f"p=pathlib.Path({rel!r});p.parent.mkdir(parents=True,exist_ok=True);p.write_text('d');"
        "g=['git','-c','user.name=t','-c','user.email=t@example.invalid'];"
        f"subprocess.run(g+['add',{rel!r}],check=True);"
        "subprocess.run(g+['commit','-qm','during'],check=True)"
    )
    return f'"{sys.executable}" -c "{code}"'


def test_head_change_during_run_fails(tmp_path):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _commit_during("src/code.py")]) == 1
    rec = record(root)
    assert rec["status"] == "fail"
    assert rec["reason"] == "실행 중 HEAD 변경"
    assert rec["start_head"] != rec["head"]
    assert close(root, note) == 1


def test_nonpositive_timeout_is_usage_error(tmp_path):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", PASS, "--timeout", "0"]) == 2
    assert suite_gate.main(["--root", str(root), "--command", PASS, "--timeout", "-1"]) == 2


def test_running_receipt_and_log_are_visible_during_command(tmp_path):
    root, _ = make_repo(tmp_path)
    command = f'"{sys.executable}" -u -c "import json; from pathlib import Path; print(\'running-marker\', flush=True); r=json.loads(Path(\'.harness/suite-gate.json\').read_text(encoding=\'utf-8\')); assert r[\'status\']==\'running\' and r[\'exit_code\'] is None and r[\'start_head\'] and r[\'started_at\'] and \'running-marker\' in Path(r[\'log\']).read_text()"'
    assert suite_gate.main(["--root", str(root), "--command", command]) == 0
    assert record(root)["status"] == "pass"


def test_record_and_log_stay_out_of_git_status(tmp_path):
    # M26 마감 감사 F3: 체크아웃 로컬 기록이 untracked 로 떠 갈래가 커밋해 버렸다 — 로컬 exclude 로 숨긴다
    root, note = make_repo(tmp_path)
    note.unlink()
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    out = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                         capture_output=True, text=True, check=True).stdout
    assert "suite-gate" not in out, out
    assert record(root)["dirty"] == 0


# ---- step-1 (M28): 기록 덮음 판정 `--check` · `--strict-clean` · `--shell bash` ----

def head_of(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def commit_file(root: Path, rel: str, text: str = "x", msg: str | None = None) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(root, "add", rel)
    git(root, "commit", "-qm", msg or f"edit {rel}")
    return head_of(root)


def passed_repo(tmp_path: Path) -> tuple[Path, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    return root, record(root)["head"]


def test_check_accepts_record_only_commits(tmp_path, capsys):
    root, recorded = passed_repo(tmp_path)
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    assert capsys.readouterr().out == "suite-gate: covered — 같은 커밋\n"

    commit_file(root, "plans/2026-11-18-x.md")
    commit_file(root, "ROADMAP.md")
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    assert capsys.readouterr().out == "suite-gate: covered — 기록 커밋 뒤 기록 파일 2개만 변경\n"
    assert record(root)["head"] == recorded  # --check 는 기록을 쓰지 않는다

    for rel in ("HANDOFF.md", "docs/BACKLOG.md", "changesets/20261118-x/README.md", "archive/reports/r.md"):
        commit_file(root, rel)
    ok, why = suite_gate.record_covers(root)
    assert ok, why
    assert why == "기록 커밋 뒤 기록 파일 6개만 변경"


def test_check_rejects_source_commit(tmp_path, capsys):
    root, _ = passed_repo(tmp_path / "a")
    commit_file(root, "plans/p.md")
    commit_file(root, "src/app.py")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("suite-gate: not covered — ")
    assert "src/app.py" in out

    # 일반 마크다운·접두만 닮은 경로는 모두 거부
    for i, rel in enumerate(("docs/guide.md", "README.md", "plans-extra/x.md", "docs/BACKLOG.mdx", "ROADMAP.md.txt")):
        root2, _ = passed_repo(tmp_path / f"r{i}")
        commit_file(root2, rel)
        assert suite_gate.record_covers(root2)[0] is False, rel


def test_check_rejects_rename_out_of_record_path(tmp_path):
    root, _ = make_repo(tmp_path)
    commit_file(root, "plans/moved.py", "print(1)\n")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    git(root, "mv", "plans/moved.py", "src_moved.py")
    git(root, "commit", "-qm", "rename out of plans")
    ok, why = suite_gate.record_covers(root)
    assert not ok and "src_moved.py" in why


def test_check_rejects_non_ancestor_record(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    first = head_of(root)
    git(root, "checkout", "-q", "-b", "side")
    side = commit_file(root, "src/side.py")
    git(root, "checkout", "-q", "-")
    commit_file(root, "src/main.py")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0  # 기록 head = main 끝
    capsys.readouterr()
    # 기록 커밋이 더 새롭거나 다른 가지 — 조상이 아니고 코드도 달라 지문도 못 덮는다(M32: 같은 코드면 지문이 덮는다)
    for target in (first, side):
        assert suite_gate.main(["--root", str(root), "--check", "--head", target]) == 1
        out = capsys.readouterr().out
        assert out.startswith("suite-gate: not covered — ")
        assert "조상" in out


def test_strict_clean_rejects_tracked_dirty_record(tmp_path, capsys):
    root, _ = passed_repo(tmp_path)
    assert record(root)["dirty_tracked"] == 0
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean"]) == 0

    # 추적 파일이 고쳐진 채 돌린 기록
    (root / "a.txt").write_text("changed", encoding="utf-8")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    rec = record(root)
    assert rec["dirty_tracked"] == 1 and rec["dirty"] == 2  # note.md(untracked)도 dirty 에는 센다
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean"]) == 1
    assert capsys.readouterr().out.startswith("suite-gate: not covered — ")
    assert suite_gate.main(["--root", str(root), "--check"]) == 0  # strict 아니면 덮는다

    # 필드가 없는 옛 기록·None 도 strict 에서는 덮지 않는다
    for missing in (False, True):
        rec = record(root)
        if missing:
            del rec["dirty_tracked"]
        else:
            rec["dirty_tracked"] = None
        (root / ".harness" / "suite-gate.json").write_text(json.dumps(rec), encoding="utf-8")
        assert suite_gate.record_covers(root, strict_clean=True)[0] is False
        assert suite_gate.record_covers(root)[0] is True


def test_check_rejects_command_mismatch(tmp_path, capsys):
    root, _ = passed_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--check", "--command", PASS]) == 0
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--command", "npm run verify:all"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("suite-gate: not covered — ")
    assert "명령" in out
    assert suite_gate.main(["--root", str(root), "--check"]) == 0  # 안 주면 묻지 않는다


def test_check_rejects_non_pass_and_missing_records(tmp_path):
    root, _ = make_repo(tmp_path)
    ok, why = suite_gate.record_covers(root)
    assert not ok and "기록" in why
    (root / ".harness").mkdir()
    (root / ".harness" / "suite-gate.json").write_text("{깨짐", encoding="utf-8")
    ok, why = suite_gate.record_covers(root)
    assert not ok and "기록" in why

    assert suite_gate.main(["--root", str(root), "--waive", "사유"]) == 0
    assert suite_gate.record_covers(root)[0] is False
    assert suite_gate.record_scope(root, None)[0] is True  # 범위만 보면 같은 커밋
    assert suite_gate.main(["--root", str(root), "--command", FAIL]) == 1
    assert suite_gate.record_covers(root)[0] is False
    assert suite_gate.record_scope(root, None)[0] is True


def test_check_non_git_root_returns_reason_not_exception(tmp_path):
    ok, why = suite_gate.record_covers(tmp_path)
    assert ok is False and why


def test_record_only_paths_are_the_six_of_d5():
    """D5 여섯 경로 + 마감 감사 뒤 사용자가 더한 archive/plans/ (닫기 커밋이 계획서를 거기로 옮긴다)."""
    assert set(suite_gate.RECORD_ONLY_PATHS) == {
        "plans/", "archive/plans/", "changesets/", "archive/reports/", "docs/reports/", "ROADMAP.md", "HANDOFF.md",
        "docs/BACKLOG.md", ".harness/work.json", ".harness/execution-ledger.jsonl",
        "docs/known-failures.md"}  # M32 V-4: 알려진 실패 목록을 고쳐도 기록이 무효가 되지 않는다


def test_check_accepts_closing_commit_shape(tmp_path, capsys):
    """/harness-done 닫기 커밋 모양 — 계획서를 archive/plans/ 로 git mv + 완료 노트 + ROADMAP — 을 덮는다.
    같은 커밋에 소스가 하나라도 끼면 덮지 않는다."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    root, _ = make_repo(tmp_path)
    commit_file(root, "plans/2026-11-18-M1-x.md", "plan")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0

    (root / "archive" / "plans").mkdir(parents=True)
    git(root, "mv", "plans/2026-11-18-M1-x.md", "archive/plans/2026-11-18-M1-x.md")
    for rel in ("archive/reports/2026-11-18-M1-x.md", "ROADMAP.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("done", encoding="utf-8")
        git(root, "add", rel)
    git(root, "commit", "-qm", "chore(roadmap): M1 완료")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean"]) == 0
    assert capsys.readouterr().out.startswith("suite-gate: covered — 기록 커밋 뒤 기록 파일 ")

    commit_file(root, "docs/design-references/readme.md")
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    assert "docs/design-references/readme.md" in capsys.readouterr().out


def test_record_covers_docs_reports_commit(tmp_path, capsys):
    """M30 step-2: 완료 노트를 docs/reports/ 에 두는 레포 — 노트 커밋이 통과 기록을 무효로 하지 않는다."""
    root, _ = passed_repo(tmp_path)
    commit_file(root, "docs/reports/2026-11-19-M1-x.md")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    assert capsys.readouterr().out == "suite-gate: covered — 기록 커밋 뒤 기록 파일 1개만 변경\n"


def test_record_does_not_cover_other_docs_folder(tmp_path, capsys):
    """Failure probe: docs 아래 다른 폴더(또는 접두만 닮은 reports-x/)는 덮지 않는다."""
    for i, rel in enumerate(("docs/guide/a.md", "docs/reports-x/a.md")):
        root, _ = passed_repo(tmp_path / f"d{i}")
        commit_file(root, rel)
        capsys.readouterr()
        assert suite_gate.main(["--root", str(root), "--check"]) == 1, rel
        assert rel in capsys.readouterr().out


def test_record_covers_committed_harness_state(tmp_path, capsys):
    """M30 마감 감사: 연쇄 승인·마감 커밋이 .harness/work.json·execution-ledger.jsonl 을 커밋한다 — 기록을 무효로 하지 않는다."""
    root, _ = passed_repo(tmp_path)
    commit_file(root, ".harness/work.json")
    commit_file(root, ".harness/execution-ledger.jsonl")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 0


def test_record_does_not_cover_other_harness_files(tmp_path, capsys):
    """Failure probe: .harness/ 아래 스크립트(검사가 읽는 소스)는 덮지 않는다."""
    root, _ = passed_repo(tmp_path)
    commit_file(root, ".harness/roadmap_sync.py")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    assert ".harness/roadmap_sync.py" in capsys.readouterr().out


def test_shell_bash_runs_subshell_compound(tmp_path):
    root, _ = make_repo(tmp_path)
    (root / "one").mkdir()
    (root / "two").mkdir()
    command = "(cd one && true) && (cd two && echo two-ran)"
    assert suite_gate.main(["--root", str(root), "--command", command, "--shell", "bash"]) == 0
    rec = record(root)
    assert rec["status"] == "pass" and rec["shell"] == "bash"
    assert "two-ran" in (root / ".harness" / "suite-gate.log").read_text(encoding="utf-8")

    # 기본 셸 동작은 그대로 — 기록의 shell 은 None
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    assert record(root)["shell"] is None


def test_shell_bash_missing_is_usage_error(tmp_path, monkeypatch, capsys):
    root, _ = make_repo(tmp_path)
    monkeypatch.setattr(suite_gate.shutil, "which", lambda name: None)
    assert suite_gate.main(["--root", str(root), "--command", PASS, "--shell", "bash"]) == 2
    assert "bash" in capsys.readouterr().err
    assert not (root / ".harness" / "suite-gate.json").exists()


def test_shell_bash_timeout_kills_tree(tmp_path):
    root, _ = make_repo(tmp_path)
    began = time.monotonic()
    assert suite_gate.main(["--root", str(root), "--command", "sleep 60 && true", "--shell", "bash", "--timeout", "1"]) == 1
    assert time.monotonic() - began < 30
    rec = record(root)
    assert rec["status"] == "fail" and rec["exit_code"] is None and rec["shell"] == "bash"


def test_check_with_waive_is_usage_error(tmp_path, capsys):
    """--check 는 판정만 한다 — --waive 를 같이 주면 면제가 기록된 줄 알 수 있으니 사용법 오류."""
    root, _ = passed_repo(tmp_path)
    before = record(root)
    assert suite_gate.main(["--root", str(root), "--check", "--waive", "사유"]) == 2
    assert record(root) == before


def test_record_scope_uses_given_record(tmp_path):
    """읽은 기록을 넘기면 파일을 다시 읽지 않는다 — 판정 도중 기록이 바뀌어도 status 와 head 가 한 기록의 것이다."""
    root, _ = passed_repo(tmp_path)
    rec = record(root)
    (root / ".harness" / "suite-gate.json").write_text("{깨진 기록", encoding="utf-8")
    assert suite_gate.record_scope(root, record=rec) == (True, "같은 커밋")
    assert suite_gate.record_scope(root)[0] is False


# ---- 2026-11-18: `--base` — 원격에 이미 있는 커밋 뒤로 기록 파일만 바뀐 push 는 기록 없이도 덮는다 ----

def test_base_covers_record_only_push_without_any_record(tmp_path, capsys):
    """다른 세션이 HANDOFF 한 줄만 넘기는 push — 스위트 기록이 없거나 옛 기록이어도 건너뛴다."""
    root, _ = make_repo(tmp_path)
    base = head_of(root)
    commit_file(root, "HANDOFF.md")
    commit_file(root, "plans/p.md")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean", "--base", base,
                            "--command", "npm run verify:all"]) == 0
    assert capsys.readouterr().out == f"suite-gate: covered — 원격 커밋 {base[:8]} 뒤 기록 파일 2개만 변경\n"
    assert not (root / ".harness" / "suite-gate.json").exists()  # 기록을 쓰지 않는다


def test_base_does_not_cover_source_change_and_falls_back_to_record(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    base = head_of(root)
    commit_file(root, "HANDOFF.md")
    commit_file(root, "src/app.py")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--base", base]) == 1  # 기록도 없다
    assert capsys.readouterr().out.startswith("suite-gate: not covered — ")
    # 기록이 덮으면 base 가 못 덮어도 통과한다
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    assert suite_gate.main(["--root", str(root), "--check", "--base", base]) == 0


def test_base_must_be_a_real_ancestor_with_changes(tmp_path):
    root, _ = make_repo(tmp_path)
    first = head_of(root)
    commit_file(root, "HANDOFF.md")
    tip = head_of(root)
    zero = "0" * 40
    assert suite_gate.base_covers(root, zero, tip)[0] is False            # 새 브랜치 push
    assert suite_gate.base_covers(root, "deadbeef" * 5, tip)[0] is False  # 로컬에 없는 원격 커밋
    assert suite_gate.base_covers(root, tip, first)[0] is False           # 조상이 아니다(되감기 push)
    assert suite_gate.base_covers(root, tip, tip)[0] is False             # 바뀐 것이 없다 — 판정 근거 없음
    assert suite_gate.base_covers(tmp_path / "nowhere", first, tip)[0] is False
    assert suite_gate.base_covers(root, first, tip)[0] is True


def test_base_requires_check(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--base", head_of(root)]) == 2


def _tracked_dirty_repo(tmp_path: Path, rel: str) -> Path:
    root, _ = make_repo(tmp_path)
    commit_file(root, rel, "v1")
    (root / rel).write_text("v2", encoding="utf-8")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    return root


def test_strict_clean_ignores_harness_state(tmp_path, capsys):
    root = _tracked_dirty_repo(tmp_path, ".harness/work.json")
    assert record(root)["dirty_tracked"] == 0
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean"]) == 0


def test_strict_clean_still_blocks_source_dirty(tmp_path, capsys):
    root = _tracked_dirty_repo(tmp_path, "src/x.py")
    assert record(root)["dirty_tracked"] == 1
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--strict-clean"]) == 1
    assert "not covered" in capsys.readouterr().out


# ---- step-3 (M30): --stream — 실행 출력을 로그에 쓰면서 표준 출력에도 실시간으로 흘린다 ----

def _echo_cmd(code: int) -> str:
    return f'"{sys.executable}" -c "print(\'hello-\' + \'stream-line\'); raise SystemExit({code})"'


def test_stream_echoes_output_and_records(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _echo_cmd(0), "--stream"]) == 0
    out = capsys.readouterr().out
    assert "hello-stream-line" in out
    assert record(root)["status"] == "pass" and record(root)["exit_code"] == 0
    assert "hello-stream-line" in (root / ".harness" / "suite-gate.log").read_text(encoding="utf-8")

    assert suite_gate.main(["--root", str(root), "--command", _echo_cmd(1), "--stream"]) == 1
    assert "hello-stream-line" in capsys.readouterr().out
    rec = record(root)
    assert rec["status"] == "fail" and rec["exit_code"] == 1


def test_without_stream_stdout_has_no_command_output(tmp_path, capsys):
    """Failure probe: --stream 없이는 성공 실행의 표준 출력에 명령 출력이 없다."""
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _echo_cmd(0)]) == 0
    assert "hello-stream-line" not in capsys.readouterr().out


def test_stream_is_line_by_line_live(tmp_path):
    """끝난 뒤 한꺼번에가 아니다 — 첫 줄이 명령이 끝나기 전에 도착한다."""
    root, _ = make_repo(tmp_path)
    cmd = f'"{sys.executable}" -c "import time; print(\'first-line\', flush=True); time.sleep(6); print(\'last\')"'
    proc = subprocess.Popen([sys.executable, str(PROMOTED / "harness-done" / "bin" / "suite_gate.py"),
                             "--root", str(root), "--command", cmd, "--stream"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    t0 = time.monotonic()
    seen = None
    for line in proc.stdout:
        if "first-line" in line:
            seen = time.monotonic() - t0
            break
    proc.communicate(timeout=60)
    assert seen is not None and seen < 5, seen


def test_stream_survives_non_utf8_output(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    cmd = f'"{sys.executable}" -c "import sys; sys.stdout.buffer.write(bytes([0xb0,0xa1,0xff,10]))"'
    assert suite_gate.main(["--root", str(root), "--command", cmd, "--stream"]) == 0
    assert record(root)["status"] == "pass"


def test_stream_timeout_still_records_fail(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    cmd = f'"{sys.executable}" -c "import time; print(\'x\', flush=True); time.sleep(30)"'
    assert suite_gate.main(["--root", str(root), "--command", cmd, "--stream", "--timeout", "2"]) == 1
    assert record(root)["status"] == "fail" and "시간 초과" in record(root)["reason"]


def test_stream_with_check_is_usage_error(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--check", "--stream"]) == 2
    assert "--stream" in capsys.readouterr().err


# ---- M32 step-1: 통과 기록을 코드 지문에 묶는다 (V-1) ----

def test_fingerprint_covers_rebased_same_code(tmp_path, capsys):
    """같은 코드를 다른 부모 위에 다시 커밋한(조상 아님) 대상도 덮는다 — 리베이스·기록 커밋 순서 뒤바뀜."""
    root, _ = make_repo(tmp_path)
    base = head_of(root)
    commit_file(root, "src/app.py", "print(1)\n")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    recorded = record(root)["head"]
    assert record(root).get("fingerprint")
    # base 위에 기록 파일을 먼저 커밋하고 같은 코드를 다시 얹는다 — recorded 는 이 커밋의 조상이 아니다
    git(root, "checkout", "-q", "-b", "rebased", base)
    commit_file(root, "HANDOFF.md", "h")
    target = commit_file(root, "src/app.py", "print(1)\n")
    assert subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", recorded, target]).returncode != 0
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--head", target]) == 0
    assert "같은 코드 지문" in capsys.readouterr().out


def test_fingerprint_changes_on_code_edit(tmp_path, capsys):
    """기록 전용 경로 밖 파일 한 줄 변경이면 덮지 않는다 — 거짓 통과를 막는 문."""
    root, _ = make_repo(tmp_path)
    base = head_of(root)
    commit_file(root, "src/app.py", "print(1)\n")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    fp = record(root)["fingerprint"]
    git(root, "checkout", "-q", "-b", "other", base)
    target = commit_file(root, "src/app.py", "print(2)\n")
    assert suite_gate.tree_fingerprint(root, target) != fp
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check", "--head", target]) == 1
    assert capsys.readouterr().out.startswith("suite-gate: not covered — ")
    # 기록 전용 경로만 다르면 지문이 같다
    git(root, "checkout", "-q", "-b", "other2", base)
    commit_file(root, "src/app.py", "print(1)\n")
    same = commit_file(root, "plans/p.md", "p")
    assert suite_gate.tree_fingerprint(root, same) == fp


def test_run_survives_record_only_commit_midway(tmp_path):
    """실행 중 기록 파일만 커밋하면 시작·끝 지문이 같아 pass — 끝 HEAD 로 기록되고 --check 가 덮는다."""
    root, _ = make_repo(tmp_path)
    start = head_of(root)
    assert suite_gate.main(["--root", str(root), "--command", _commit_during("changesets/x.md")]) == 0
    rec = record(root)
    assert rec["status"] == "pass"
    assert rec["start_head"] == start and rec["head"] == head_of(root) != start
    assert rec["fingerprint"] == suite_gate.tree_fingerprint(root, start)
    assert suite_gate.main(["--root", str(root), "--check"]) == 0


def test_run_fails_on_code_commit_midway(tmp_path):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _commit_during("src/code.py")]) == 1
    rec = record(root)
    assert rec["status"] == "fail" and rec["reason"] == "실행 중 HEAD 변경"


def test_legacy_record_without_fingerprint(tmp_path, capsys):
    """지문 없는 옛 기록은 옛 판정(같은 커밋·조상+기록 파일만) 그대로 — 조상 아닌 같은 코드는 덮지 않는다."""
    root, _ = make_repo(tmp_path)
    base = head_of(root)
    commit_file(root, "src/app.py", "print(1)\n")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    path = root / ".harness" / "suite-gate.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec.pop("fingerprint")
    path.write_text(json.dumps(rec), encoding="utf-8")
    commit_file(root, "ROADMAP.md")
    assert suite_gate.record_covers(root) == (True, "기록 커밋 뒤 기록 파일 1개만 변경")
    git(root, "checkout", "-q", "-b", "rebased", base)
    target = commit_file(root, "src/app.py", "print(1)\n")
    ok, why = suite_gate.record_covers(root, target)
    assert not ok and "조상" in why


# ---- M32 step-2: 알려진 실패와 대조해 새 실패만 막는다 (V-4) ----

PYTEST_FAIL_OUT = """\
tests/test_a.py::test_ok PASSED
=========================== short test summary info ============================
FAILED tests/test_a.py::test_flaky_net - ConnectionError: boom
FAILED tests/test_b.py::TestX::test_win_path[case-1]
2 failed, 1 passed in 0.5s
"""


def _fail_with(text: str) -> str:
    """주어진 출력을 내고 exit 1 로 끝나는 명령."""
    return f'"{sys.executable}" -c "import sys;sys.stdout.write({text!r});sys.exit(1)"'


def _known(root: Path, *lines: str) -> None:
    path = root / "docs" / "known-failures.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 알려진 실패\n\n" + "".join(f"{ln}\n" for ln in lines), encoding="utf-8")


def test_extract_failure_names():
    assert suite_gate.extract_failure_names(PYTEST_FAIL_OUT) == [
        "tests/test_a.py::test_flaky_net", "tests/test_b.py::TestX::test_win_path[case-1]"]
    cargo = "running 3 tests\ntest net::tests::fetch_ok ... ok\ntest net::tests::fetch_retry ... FAILED\n\nfailures:\n"
    assert suite_gate.extract_failure_names(cargo) == ["net::tests::fetch_retry"]
    tap = "ok 1 - parses\nnot ok 2 - renders korean path\n"
    assert suite_gate.extract_failure_names(tap) == ["renders korean path"]
    node = "✔ parses (1ms)\n✖ renders korean path (3ms)\n"
    assert suite_gate.extract_failure_names(node) == ["renders korean path"]
    jest = "PASS src/a.test.js\nFAIL src/b.test.js\n"
    assert suite_gate.extract_failure_names(jest) == ["src/b.test.js"]
    assert suite_gate.extract_failure_names("Traceback: boom\nexit 1\n") == []


def test_known_failures_only_covers(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(PYTEST_FAIL_OUT)]) == 1
    rec = record(root)
    assert rec["status"] == "fail" and len(rec["failures"]) == 2
    _known(root, "- test_flaky_net — 네트워크 의존, main 에서도 빨강 (2026-11-19)",
           "- test_win_path — Windows 경로, main 에서도 빨강 (2026-11-19)")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    assert "covered — 알려진 실패만 2건" in capsys.readouterr().out
    # 목록 파일을 커밋해도 기록이 무효가 되지 않는다 (RECORD_ONLY_PATHS)
    git(root, "add", "docs/known-failures.md")
    git(root, "commit", "-qm", "known")
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    # 마감도 면제 없이 닫힌다 — 단 §3 에 `스위트: 알려진 실패 — …` 줄이 있어야 사용자가 뒤집을 자리가 생긴다(감사 권고)
    assert close(root, note) == 1
    note.write_text(NOTE.format(extra="- 스위트: 알려진 실패 — test_flaky_net·test_win_path (main 에서도 빨강)"), encoding="utf-8")
    assert close(root, note) == 0


def test_new_failure_not_covered(tmp_path, capsys):
    root, note = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(PYTEST_FAIL_OUT)]) == 1
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1  # 목록 파일 없음
    _known(root)  # 빈 목록
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    _known(root, "- test_flaky_net — 네트워크 (2026-11-19)")  # 하나는 목록 밖
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    out = capsys.readouterr().out
    assert "not covered" in out and "test_win_path" in out
    assert close(root, note) == 1


def test_no_failure_names_not_covered(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with("Traceback: boom\n")]) == 1
    assert record(root)["failures"] == []
    _known(root, "- boom — 아무거나 (2026-11-19)")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    assert "실패 이름" in capsys.readouterr().out


def test_stale_known_failure_reported(tmp_path, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(PYTEST_FAIL_OUT)]) == 1
    _known(root, "- test_flaky_net — 네트워크 (2026-11-19)", "- test_win_path — 경로 (2026-11-19)",
           "- test_fixed_long_ago — 이미 고쳐짐 (2026-10-01)")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    out = capsys.readouterr().out
    assert "목록에서 지울 후보" in out and "test_fixed_long_ago" in out


# ---- M32 마감 리뷰 반영: 거짓 통과 경계 ----

def _code_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root, _ = make_repo(tmp_path)
    commit_file(root, "src/app.py", "print(1)\n")
    commit_file(root, "src/keep.py", "k\n")
    assert suite_gate.main(["--root", str(root), "--command", PASS]) == 0
    return root, head_of(root), record(root)["fingerprint"]


@pytest.mark.parametrize("change", ["delete", "add", "chmod", "rename"])
def test_fingerprint_differs_on_any_code_change(tmp_path, change):
    root, recorded, fp = _code_repo(tmp_path)
    if change == "delete":
        git(root, "rm", "-q", "src/keep.py")
    elif change == "add":
        (root / "src" / "new.py").write_text("n\n", encoding="utf-8")
        git(root, "add", "src/new.py")
    elif change == "chmod":
        git(root, "update-index", "--chmod=+x", "src/app.py")
    else:
        git(root, "mv", "src/keep.py", "src/kept.py")
    git(root, "commit", "-qm", change)
    target = head_of(root)
    assert suite_gate.tree_fingerprint(root, target) != fp
    assert suite_gate._fingerprint_covers(root, record(root), target) is False


def test_known_key_substring_does_not_cover_other_tests(tmp_path, capsys):
    """목록 키가 실패 이름의 일부 문자열일 뿐이면(같은 접두의 다른 테스트) 덮지 않는다 — 경계(::·[)에서만."""
    out = "FAILED tests/test_a.py::test_x_new_regression - boom\n1 failed in 0.1s\n"
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(out)]) == 1
    _known(root, "- test_x — 플레이키 (2026-11-19)")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    # 파라미터 변형은 키가 경계(`[`)에서 끝나면 덮는다
    out2 = "FAILED tests/test_a.py::test_x[case-1] - boom\n1 failed in 0.1s\n"
    (tmp_path / "b").mkdir()
    root2, _ = make_repo(tmp_path / "b")
    assert suite_gate.main(["--root", str(root2), "--command", _fail_with(out2)]) == 1
    _known(root2, "- test_x — 플레이키 (2026-11-19)")
    assert suite_gate.main(["--root", str(root2), "--check"]) == 0


def test_short_or_placeholder_keys_ignored(tmp_path):
    root, _ = make_repo(tmp_path)
    _known(root, "- test — 너무 짧다 (2026-11-19)", "- 예시 줄 설명", "- `tests/test_a.py::test_flaky_net` — 네트워크 (2026-11-19)")
    assert suite_gate.load_known_failures(root) == ["tests/test_a.py::test_flaky_net"]


@pytest.mark.parametrize("out", [
    # 이름을 뽑은 알려진 실패 + 수집 오류(ERROR)
    "FAILED tests/test_a.py::test_flaky_net - boom\nERROR tests/b.py - ImportError\n1 failed, 1 error in 0.1s\n",
    # 이름 일부만 뽑힌다 — 요약 수와 다름
    "FAILED tests/test_a.py::test_flaky_net - boom\n2 failed in 0.1s\n",
])
def test_partial_extraction_not_covered(tmp_path, out, capsys):
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(out)]) == 1
    _known(root, "- test_flaky_net — 네트워크 (2026-11-19)")
    capsys.readouterr()
    assert suite_gate.main(["--root", str(root), "--check"]) == 1


def test_failed_id_with_spaces_extracted():
    out = "FAILED t.py::test_new[a b] - boom\n1 failed in 0.1s\n"
    assert suite_gate.extract_failure_names(out) == ["t.py::test_new[a b]"]


def test_early_stop_run_not_covered(tmp_path):
    """-x·--maxfail 로 중간에 멈춘 실행은 남은 테스트가 안 돌았으니 덮지 않는다."""
    out = "FAILED tests/test_a.py::test_flaky_net - boom\n1 failed in 0.1s\n"
    root, _ = make_repo(tmp_path)
    cmd = _fail_with(out) + " -x"
    assert suite_gate.main(["--root", str(root), "--command", cmd]) == 1
    assert record(root)["failures"] == []
    _known(root, "- test_flaky_net — 네트워크 (2026-11-19)")
    assert suite_gate.main(["--root", str(root), "--check"]) == 1


def test_fail_with_code_commit_midway_not_covered(tmp_path):
    """실패한 실행 중 코드가 커밋되면 알려진 실패만이어도 덮지 않는다 — 돈 코드가 닫는 코드가 아니다."""
    out = "FAILED tests/test_a.py::test_flaky_net - boom\n1 failed in 0.1s\n"
    code = (
        "import pathlib,subprocess,sys;"
        "p=pathlib.Path('src/code.py');p.parent.mkdir(parents=True,exist_ok=True);p.write_text('d');"
        "g=['git','-c','user.name=t','-c','user.email=t@example.invalid'];"
        "subprocess.run(g+['add','src/code.py'],check=True);"
        "subprocess.run(g+['commit','-qm','during'],check=True);"
        f"sys.stdout.write({out!r});sys.exit(1)"
    )
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", f'"{sys.executable}" -c "{code}"']) == 1
    _known(root, "- test_flaky_net — 네트워크 (2026-11-19)")
    ok, why = suite_gate.record_covers(root)
    assert not ok


# ---- M32 마감 감사 반영: 요약 수가 없거나 복합 명령이면 덮지 않는다 ----

def test_no_summary_count_not_covered(tmp_path):
    """러너 요약(실패 수)을 못 읽으면 이름 일부만 뽑혔을 수 있다 — 덮지 않는다."""
    root, _ = make_repo(tmp_path)
    out = "  FAIL verify:mobile-check (exit 1)\n게이트가 인덱스에 올린 경로 1개:\n  x.txt\n"
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(out)]) == 1
    assert record(root)["failures"] == []
    _known(root, "- verify:mobile-check — 기기 의존 (2026-11-20)")
    assert suite_gate.main(["--root", str(root), "--check"]) == 1


def test_verify_all_fails_summary(tmp_path):
    """a-private-repo verify:all 요약 `FAILS N` 을 읽는다 — 수가 맞으면 덮고, 잔여물 FAIL 이 끼면 덮지 않는다."""
    ok_out = "FAILS 1\n\n  FAIL verify:mobile-check (exit 1)\n        tail\n        log: x\n"
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(ok_out)]) == 1
    _known(root, "- verify:mobile-check — 기기 의존 (2026-11-20)")
    assert suite_gate.main(["--root", str(root), "--check"]) == 0
    leak_out = "FAILS 2\n\n  FAIL verify:mobile-check (exit 1)\n\n  FAIL index-leak (게이트가 인덱스에 올린 경로 1개)\n"
    (tmp_path / "b").mkdir()
    root2, _ = make_repo(tmp_path / "b")
    assert suite_gate.main(["--root", str(root2), "--command", _fail_with(leak_out)]) == 1
    _known(root2, "- verify:mobile-check — 기기 의존 (2026-11-20)")
    assert suite_gate.main(["--root", str(root2), "--check"]) == 1


def test_compound_command_not_covered(tmp_path):
    """`a && b` 에서 a 가 알려진 실패로 멈추면 b 는 돌지 않았다 — 덮지 않는다(따옴표 안의 ; 는 복합이 아니다)."""
    out = "FAILED tests/test_a.py::test_flaky_net - boom\n1 failed in 0.1s\n"
    root, _ = make_repo(tmp_path)
    assert suite_gate.main(["--root", str(root), "--command", _fail_with(out) + " && echo later"]) == 1
    assert record(root)["failures"] == []
    _known(root, "- test_flaky_net — 네트워크 (2026-11-20)")
    assert suite_gate.main(["--root", str(root), "--check"]) == 1
    assert suite_gate.is_compound(_fail_with(out)) is False
