#!/usr/bin/env python3
"""report_close.py 회귀 테스트 (HQ3 step-2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report_close  # noqa: E402


def make_report(path: Path, *, empty_evidence: bool = False, no_smoke: bool = False) -> None:
    evidence = "" if empty_evidence else (
        "- changesets/20260721-hq3-report-template · changesets/20260721-hq3-ledger-derivation\n"
        "- pytest scripts -q PASS\n"
        + ("" if no_smoke else "- 실표면: 배포된 report_close 를 실보고서로 구동 — 3-event 파생 관측\n")
        + "- 재현: python report_close.py <report> --task-id T1 --root .\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# 최종 보고서 — 테스트

## 1. 문제 정의 (무엇을 왜 하려 했나)
완료 의식이 비대했다.

## 2. Objective 연결 (북극성과의 관계)
동기화 축을 움직였다.

## 3. 경로 (horizon → milestone → steps)
HQ3 step-1~3.

## 4. 구현 결과 (무엇이 만들어졌나)
보고서가 완료 의식의 정본이 됐다.

## 5. 이슈와 해결 (막혔던 것, 어떻게 풀었나)
없음.

## 6. 결과물과 증거 (검증 포함)
{evidence}

## 7. 후속 제안 (다음에 무엇을)
다음 horizon 에서 실사용 관측.
""",
        encoding="utf-8",
    )


def make_work(root: Path, task_id: str = "T1") -> Path:
    work = root / ".harness" / "work.json"
    work.parent.mkdir(parents=True, exist_ok=True)
    work.write_text(
        json.dumps({"active_work_id": task_id, "works": {task_id: {"work_id": task_id, "status": "active"}}}),
        encoding="utf-8",
    )
    return work


def read_events(root: Path) -> list[dict]:
    ledger = root / ".harness" / "execution-ledger.jsonl"
    return [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_valid_report_derives_three_events_and_completes_work(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report)
    work = make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--summary", "요약 한 문장"])
    assert rc == 0
    events = read_events(tmp_path)
    assert [e["event"] for e in events] == ["done_claim", "adversarial_verify", "task_completed"]
    assert events[1]["verdict"] == "confirmed"
    assert events[1]["surface_smoke"].startswith("배포된")
    assert events[0]["worker"] != events[1]["verifier"]  # 독립성 계약 보존
    state = json.loads(work.read_text(encoding="utf-8"))
    assert state["works"]["T1"]["status"] == "completed"
    assert state["works"]["T1"]["completion_summary"] == "요약 한 문장"
    assert state["active_work_id"] == "T1"  # 포인터는 비우지 않는다 (Stop 훅 완료 알림)


# 2026-08-06 감사 T2: 위 `worker != verifier` 는 기본값이 `report-author:T1` /
# `report-verifier:T1` 이라 **인자를 주지 않는 한 실패할 수 없는** 동어반복이었다.
# 독립성 계약을 실제로 시험하려면 같은 이름을 밀어 넣고 거절되는지 봐야 한다
# (거절 주체는 ledger_append.build_verify — "verifier must be independent").
def test_same_worker_and_verifier_refused(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report)
    make_work(tmp_path)
    rc = report_close.main([
        str(report), "--task-id", "T1", "--root", str(tmp_path),
        "--worker", "claude", "--verifier", "claude",
    ])
    assert rc == 1
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()  # 이벤트 미기록


def test_empty_section_refused(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    make_report(report, empty_evidence=True)
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)])
    assert rc == 1
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()  # 이벤트 미기록


def test_missing_surface_smoke_refused(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    make_report(report, no_smoke=True)
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)])
    assert rc == 1
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_placeholder_template_refused(tmp_path: Path) -> None:
    # 템플릿 원본( placeholder {} 그대로 )은 거부돼야 한다
    template = Path(__file__).resolve().parents[1] / "templates" / "REPORT_TEMPLATE.md"
    report = tmp_path / "r.md"
    report.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)])
    assert rc == 1


# CF6 step-3 (2026-07-22): 7섹션 → 3섹션. 구 형식(기록 동결)도 계속 파싱돼야 한다.
SHORT_REPORT = """# 완료 — CF6 의식 다이어트

## 1. 결과
보고서 의식을 3섹션으로 줄였다.

## 2. 이슈와 해결
없음

## 3. 증거
- changeset: `changesets/20260722-cf6-report-retire`
- 검증: pytest -q PASS
- 실표면: report_close 를 새 짧은 형식으로 구동해 3-event 파생 관측
- 재현: python report_close.py <report> --task-id CF6 --root .
"""


def test_short_three_section_report_is_accepted():
    sections = report_close.split_sections(SHORT_REPORT)
    assert report_close.section_errors(sections) == []
    assert report_close.extract_line(sections["증거"], "실표면")
    assert report_close.extract_line(sections["증거"], "재현")


def test_legacy_seven_section_titles_still_parse():
    """구 보고서(2026-07-21 이전)는 기록 동결이라 고쳐 쓰지 않는다 — 계속 읽혀야 한다."""
    legacy = SHORT_REPORT.replace("## 1. 결과", "## 4. 구현 결과 (무엇이 만들어졌나)").replace(
        "## 3. 증거", "## 6. 결과물과 증거 (검증 포함)")
    sections = report_close.split_sections(legacy)
    assert report_close.section_errors(sections) == []


def test_missing_surface_smoke_still_rejected():
    """의식을 줄여도 검증 기록 요구는 남는다."""
    sections = report_close.split_sections(SHORT_REPORT.replace(
        "- 실표면: report_close 를 새 짧은 형식으로 구동해 3-event 파생 관측\n", ""))
    assert report_close.extract_line(sections["증거"], "실표면") == ""


def test_empty_section_still_rejected():
    sections = report_close.split_sections(SHORT_REPORT.replace("보고서 의식을 3섹션으로 줄였다.", ""))
    assert any("결과" in e for e in report_close.section_errors(sections))


# ── OI3 step-3: 평가 못 한 검사는 통과가 아니다 ──────────────────────────────
# dryforge go/SKILL.md:334-341 — "An unevaluable check is a fail, not a pass."
# 이 게이트가 하는 일은 하나: **조용히 통과하는 것**을 막는다. 판정은 사람이 한다.

def test_clean_evidence_passes():
    assert report_close.unevaluable_error(
        "- pytest 546 passed / 3 skipped\n- doctor FAIL 0", "bash setup.sh (exit 0, 72건)") == ""


def test_unevaluable_line_without_declaration_is_refused():
    err = report_close.unevaluable_error("- 소급 거짓 차단은 측정 불가", "ok (exit 0)")
    assert err and "평가하지 못한 검사" in err
    assert "평가 못 함:" in err          # 무엇을 하라는지 안내한다


def test_declared_unevaluable_passes():
    """표면화하면 통과 — 이 게이트는 판정이 아니라 침묵 방지다."""
    assert report_close.unevaluable_error(
        "- 평가 못 함: work.json 이 gitignored 라 소급 재현 불가\n- 소급 거짓 차단은 측정 불가",
        "ok (exit 0)") == ""


def test_side_effect_claim_in_surface_smoke_is_refused():
    """부작용에서 통과를 추론하는 경로 — 이걸 통과로 세면 게이트가 무의미하다."""
    err = report_close.unevaluable_error("- pytest ok", "스크립트를 돌렸고 에러가 안 났다")
    assert err and "부작용으로 통과를 주장" in err


def test_none_surface_smoke_is_not_a_side_effect_claim():
    assert report_close.unevaluable_error("- pytest ok", "none — 구동 가능한 서버 없음") == ""


def test_real_reports_in_this_repo_still_close():
    """정합 상태 오탐 0 — 오늘 쓴 완료 보고 3건이 새 게이트를 통과해야 한다."""
    root = Path.home() / "projects" / "the-source-repo" / "archive" / "reports"
    if not root.is_dir():
        return
    checked = 0
    for report in sorted(root.glob("2026-07-2*.md")):
        text = report.read_text(encoding="utf-8", errors="replace")
        sections = report_close.split_sections(text)
        body = sections.get("증거") or ""
        if not body.strip():
            continue
        smoke = report_close.extract_line(body, "실표면") or ""
        assert report_close.unevaluable_error(body, smoke) == "", report.name
        checked += 1
    assert checked >= 3


def test_declaration_survives_markdown_emphasis():
    """`- **평가 못 함**: …` 도 선언이다 — 게이트가 서식을 감시하면 안 된다(첫 실사용 실측)."""
    assert report_close.unevaluable_error(
        "- **평가 못 함**: work.json 이 gitignored 라 소급 재현 불가\n- 측정 불가", "ok") == ""


# ── 만든 것 ≠ 검증한 것 (2026-07-23 DC4) ─────────────────────────────────────
# OI3 은 *검사가 못 돈* 경우를 막았고, 이건 *검사를 안 만든* 경우를 말하게 한다.

def test_verification_line_with_run_evidence_passes():
    assert report_close.unverified_error("- 검증: `pytest -q` 539 passed · doctor FAIL 0\n") == ""
    assert report_close.unverified_error("- 검증: 주입 프로브 3단 실측, 오탐 0건\n") == ""


def test_bare_verification_claim_is_refused():
    """'검증: 잘 동작함' 은 검증이 아니라 주장이다."""
    err = report_close.unverified_error("- 검증: 잘 동작하는 것을 확인했다\n")
    assert "실행 근거가 없다" in err, err


def test_unverified_declaration_is_accepted():
    """테스트를 안 만들었으면 그렇게 적으면 통과한다 — 막지 않고 말하게 한다."""
    body = "- 검증: 수동 확인만 함\n- 구현됨·미검증: 회귀 테스트 없음 — 다음 milestone 에서 박는다\n"
    assert report_close.unverified_error(body) == ""
    # 마크다운 강조가 붙어도 선언이다(OI3 첫 실사용에서 겪은 서식 감시 회귀 방지)
    body2 = "- 검증: 수동 확인만 함\n- **구현됨·미검증**: 회귀 테스트 없음\n"
    assert report_close.unverified_error(body2) == ""


def test_real_reports_still_pass_unverified_gate():
    """정합 상태 오탐 0 — 이 레포의 최근 완료 보고가 새 게이트를 통과해야 한다."""
    root = Path.home() / "projects" / "the-source-repo" / "archive" / "reports"
    if not root.is_dir():
        return
    checked = 0
    for report in sorted(root.glob("2026-07-2*.md")):
        body = report_close.split_sections(report.read_text(encoding="utf-8", errors="replace")).get("증거") or ""
        if not body.strip():
            continue
        assert report_close.unverified_error(body) == "", report.name
        checked += 1
    assert checked >= 3
