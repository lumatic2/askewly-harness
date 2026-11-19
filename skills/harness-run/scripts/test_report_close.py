#!/usr/bin/env python3
"""report_close.py 회귀 테스트 (HQ3 step-2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report_close  # noqa: E402

CHR_NL = chr(10)


def make_report(path: Path, *, empty_evidence: bool = False, no_smoke: bool = False,
                harvest: str | None = "없음", audit: str | None = "none — 조건 미해당") -> None:
    evidence = "" if empty_evidence else (
        "- changesets/20260721-hq3-report-template · changesets/20260721-hq3-ledger-derivation\n"
        "- pytest scripts -q PASS\n"
        + ("" if no_smoke else "- 실표면: 배포된 report_close 를 실보고서로 구동 — 3-event 파생 관측\n")
        + "- 재현: python report_close.py <report> --task-id T1 --root .\n"
        + ("" if audit is None else f"- 감사: {audit}\n")
        + ("" if harvest is None else f"- 수확: {harvest}\n")
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
    # 2026-09-21: 템플릿 정본은 harness-done 스킬 디렉터리(harness-run 의 고아 사본은 제거)
    template = Path(__file__).resolve().parents[2] / "harness-done" / "templates" / "REPORT_TEMPLATE.md"
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
- 수확: 없음
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
    root = Path.home() / "projects" / "the-orchestration-repo" / "harness" / "archive" / "reports"
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
    root = Path.home() / "projects" / "the-orchestration-repo" / "harness" / "archive" / "reports"
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


# ── M6 step-1: kg 수확 후보를 검사 가능한 대상으로 (2026-08-20) ───────────────
# 누락은 규율 문제가 아니라 **관측 가능성** 문제였다 — 빠뜨려도 보고서가 정상으로 닫혔다.

def test_missing_harvest_line_passes(tmp_path: Path) -> None:
    # 2026-09-21 절차 다이어트: `수확:` 은 선택 — 없어도 닫힌다(구 test_missing_harvest_line_refused 반전).
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, harvest=None)
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) == 0


def test_harvest_help_states_full_format() -> None:
    """거부 메시지 하나로 형식을 다 알 수 있어야 한다 — 레포별 템플릿 사본은 안 따라온다(D2)."""
    help_text = report_close.HARVEST_HELP
    assert "수확: 없음" in help_text
    assert "출처" in help_text
    assert "형식" in help_text


def test_bare_harvest_none_passes(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, harvest="없음")
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) == 0


def test_harvest_none_with_reason_is_not_unevaluable(tmp_path: Path) -> None:
    """`없음 — n=1 이라 일반화 확인 불가` 는 분류 판정이지 못 돌린 검사가 아니다(B2)."""
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, harvest="없음 — n=1 이라 일반화 확인 불가")
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) == 0


def test_harvest_notation_variants_parse_identically() -> None:
    for notation in ("수확: 없음", "- 수확: 없음", "**수확**: 없음", "- **수확**: 없음"):
        body = "- 검증: pytest -q PASS@" + notation + "@"
        assert report_close.extract_line(body.replace("@", CHR_NL), "수확") == "없음", notation


def test_existing_lines_survive_notation_variants() -> None:
    """기존 4줄도 같은 표기 4종에서 무회귀 — 이번 완화의 회귀 표면은 신규 줄보다 넓다."""
    for prefix, value in (("실표면", "ok (exit 0)"), ("재현", "pytest -q"),
                          ("검증", "pytest -q PASS"), ("정리", "없음")):
        for pattern in ("{p}: {v}", "- {p}: {v}", "**{p}**: {v}", "- **{p}**: {v}"):
            body = pattern.format(p=prefix, v=value) + CHR_NL
            assert report_close.extract_line(body, prefix) == value, (prefix, pattern)


def test_harvest_line_excluded_from_unevaluable_scan() -> None:
    body = "- pytest 226 passed" + CHR_NL + "- 수확: 없음 — 재현 불가한 일회성 관측이라 일반화 못 함" + CHR_NL
    assert report_close.unevaluable_error(body, "ok (exit 0)") == ""
    # 다른 줄의 같은 신호는 여전히 잡힌다
    body2 = body + "- 소급 차단은 측정 불가" + CHR_NL
    assert "평가하지 못한 검사" in report_close.unevaluable_error(body2, "ok (exit 0)")


# ── M6 코드 리뷰 수리 (2026-08-20) ────────────────────────────────────────────
# 표기 완화가 값의 머리글자까지 먹었고, 줄 존재만 보던 검사가 템플릿 placeholder 를
# 통과시켰다. 셋 다 "판정을 안 한 것이 판정으로 기록되는" 같은 실패 모드다.

def test_value_keeps_its_own_leading_dashes() -> None:
    """`재현: --pre-approval 로 재실행` 이 원장에 그대로 들어가야 한다."""
    for line, expect in (
        ("- 재현: --pre-approval 로 재실행", "--pre-approval 로 재실행"),
        ("- 정리: _tmp 삭제", "_tmp 삭제"),
        ("- 실표면: -- 없음", "-- 없음"),
        ("- **재현**: --json 으로 재실행", "--json 으로 재실행"),
    ):
        prefix = line.split(":")[0].strip().lstrip("-* ").replace("*", "")
        assert report_close.extract_line(line + CHR_NL, prefix) == expect, line


def test_colonless_prose_does_not_shadow_the_field() -> None:
    """`- 재현 불가한 …` 은 산문이지 `재현:` 필드가 아니다."""
    body = "- 재현 불가한 일회성 관측이 있었다" + CHR_NL + "- 재현: pytest -q" + CHR_NL
    assert report_close.extract_line(body, "재현") == "pytest -q"


def test_template_placeholder_is_not_a_filled_line(tmp_path: Path) -> None:
    """템플릿의 `{…}` 를 그대로 둔 보고서는 판정을 안 한 것이다 — 닫히면 안 된다."""
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, harvest="{이 milestone 에서 kg 로 올릴 후보 — 없으면 없음}")
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) == 1
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_harvest_exemption_requires_the_colon() -> None:
    """`수확:` 예외가 OI3 게이트의 우회로가 되면 안 된다."""
    body = "- 수확물 정리: 측정 불가" + CHR_NL
    assert "평가하지 못한 검사" in report_close.unevaluable_error(body, "ok (exit 0)")


# ── ADR 0015 §6: `감사:` 는 `실표면:`·`재현:` 과 같은 강도의 거부 대상 (2026-09-22) ──────
# 마감 감사 자리를 세운 것만으로는 생략이 보이지 않는다 — 안 돌린 마감도 사유를 적어야 닫힌다.

def test_missing_audit_line_refused(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, audit=None)
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) != 0


def test_audit_none_with_reason_passes(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, audit="none — 스폰 조건 미해당")
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) == 0


def test_audit_placeholder_refused(tmp_path: Path) -> None:
    """템플릿 표식이 그대로면 판정을 안 한 것이다 — 채운 것으로 통과시키지 않는다."""
    report = tmp_path / "archive" / "reports" / "r.md"
    make_report(report, audit="{마감 감사자 지적 n건과 처분}")
    make_work(tmp_path)
    assert report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)]) != 0


# ── M24 step-1 (2026-11-03): 중단(dropped) 종결 ─────────────────────────────
def make_drop_report(path: Path, *, reason: str = "서면평가 미선발로 대회 진행이 끝났다.\n- 근거: 주최 측 결과 메일 2026-11-02") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# 중단 노트 — 테스트\n\n"
        f"## 1. 중단 사유\n{reason}\n\n"
        "## 2. 동결 산출물\n- submissions/ 제출본 (커밋 abc123)\n\n"
        "## 3. 재개 조건\n다음 회차 공고가 나면 새 milestone 으로.\n",
        encoding="utf-8",
    )


def test_drop_records_task_dropped_only(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    work = make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"])
    assert rc == 0
    events = read_events(tmp_path)
    assert [e["event"] for e in events] == ["task_dropped"]
    assert events[0]["task_id"] == "T1"
    assert events[0]["basis"] == "주최 측 결과 메일 2026-11-02"
    state = json.loads(work.read_text(encoding="utf-8"))
    assert state["works"]["T1"]["status"] == "dropped"


def test_drop_without_work_records_milestone(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    rc = report_close.main([str(report), "--task-id", "M9", "--milestone-id", "M9",
                            "--root", str(tmp_path), "--drop"])
    assert rc == 0
    events = read_events(tmp_path)
    assert [e["event"] for e in events] == ["task_dropped"]
    assert events[0]["milestone_id"] == "M9"
    assert not (tmp_path / ".harness" / "work.json").exists()


def test_drop_rejects_missing_reason(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report, reason="")
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"])
    assert rc != 0
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_drop_rejects_missing_basis_line(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report, reason="외부 결과로 접는다.")
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"])
    assert rc != 0


def test_completion_path_rejects_drop_note(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path)])
    assert rc != 0


def test_drop_rejects_placeholder_reason_with_basis(tmp_path: Path) -> None:
    # 감사 지적 1: 근거만 채우고 사유는 템플릿 그대로면 거부한다
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report, reason="{무엇 때문에 접나 — 한두 문장}\n- 근거: 주최 측 메일")
    make_work(tmp_path)
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"])
    assert rc != 0
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_drop_rejects_completed_work(tmp_path: Path) -> None:
    # 감사 지적 2: 이미 완료된 work 를 dropped 로 덮지 않는다
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    work = make_work(tmp_path)
    state = json.loads(work.read_text(encoding="utf-8"))
    state["works"]["T1"]["status"] = "completed"
    work.write_text(json.dumps(state), encoding="utf-8")
    rc = report_close.main([str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"])
    assert rc != 0
    assert json.loads(work.read_text(encoding="utf-8"))["works"]["T1"]["status"] == "completed"
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_drop_rejects_completed_roadmap_marker(tmp_path: Path) -> None:
    # work 가 없어도 ROADMAP 마커가 completed 면 ledger 를 쓰기 전에 거부한다
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    (tmp_path / "ROADMAP.md").write_text('<!-- harness:milestone id="M9" status="completed" -->\n', encoding="utf-8")
    rc = report_close.main([str(report), "--task-id", "M9", "--root", str(tmp_path), "--drop"])
    assert rc != 0
    assert not (tmp_path / ".harness" / "execution-ledger.jsonl").exists()


def test_drop_twice_appends_once(tmp_path: Path) -> None:
    report = tmp_path / "archive" / "reports" / "d.md"
    make_drop_report(report)
    make_work(tmp_path)
    args = [str(report), "--task-id", "T1", "--root", str(tmp_path), "--drop"]
    assert report_close.main(args) == 0
    assert report_close.main(args) == 0
    assert [e["event"] for e in read_events(tmp_path)] == ["task_dropped"]


def test_audit_and_review_lines_naming_unevaluable_condition_pass():
    """`감사: none — …` 에 스폰 조건 이름(「평가 못 함」)을 적어도 거부되지 않는다 (2026-11-16 — 문구 함정 제거)."""
    body = (
        "- 검증: pytest 12 passed\n"
        "- 감사: none — 장치 신설·교차 레포·위험 leaf·평가 못 함 모두 해당 없음\n"
        "- 리뷰: 정확성 2건 반영, 평가 못 함 없음\n"
    )
    assert report_close.unevaluable_error(body, "none — 내부") == ""
    # 다른 줄의 미평가 신호는 여전히 잡는다
    assert report_close.unevaluable_error(body + "- 실측: 평가 못 함\n", "none — 내부") != ""


# --- M28 step-3: 스위트 기록 덮음 판정 -----------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    import subprocess
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def _commit_file(root: Path, rel: str, body: str = "x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _git(root, "add", rel)
    _git(root, "commit", "-qm", rel)


def _repo_with_pass_record(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _commit_file(root, "a.py")
    head = _git(root, "rev-parse", "HEAD").strip()
    (root / ".harness").mkdir()
    (root / ".harness" / "suite-gate.json").write_text(json.dumps(
        {"status": "pass", "head": head, "command": "pytest -q", "dirty": 0, "dirty_tracked": 0}), encoding="utf-8")
    return root


def test_suite_record_accepted_after_record_only_commit(tmp_path: Path) -> None:
    root = _repo_with_pass_record(tmp_path)
    _commit_file(root, "archive/reports/n.md")
    _commit_file(root, "plans/p.md")
    error, summary = report_close.suite_gate_check(root, "")
    assert error is None
    assert summary == "스위트 통과: pytest -q (dirty 0) — 기록 커밋 뒤 기록 파일 2개만 변경"


def test_suite_record_rejected_after_source_commit(tmp_path: Path) -> None:
    root = _repo_with_pass_record(tmp_path)
    _commit_file(root, "plans/p.md")
    _commit_file(root, "src/b.py")
    error, summary = report_close.suite_gate_check(root, "")
    assert summary is None
    assert "스위트 기록이 다른 커밋의 것이다(" in error
    assert "기록 커밋 뒤 기록 파일 밖이 바뀌었다: src/b.py" in error
    assert "다시 돌린다: python " in error


def test_suite_record_same_commit_summary_unchanged(tmp_path: Path) -> None:
    root = _repo_with_pass_record(tmp_path)
    assert report_close.suite_gate_check(root, "") == (None, "스위트 통과: pytest -q (dirty 0)")
