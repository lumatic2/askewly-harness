#!/usr/bin/env python3
"""Regression tests for harness_work_state.py.

Run: pytest -q scripts/test_harness_work_state.py
"""

from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_work_state as state  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_plan_checklist_counts_step_tree_and_ignores_nested(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    write(
        plan,
        "\n".join(
            [
                "# PLAN",
                "",
                "## Step 트리",
                "- [x] **step-1** done",
                "- [ ] **step-2** next",
                "  - [ ] nested acceptance item",
                "- [ ] **step-3** later",
                "",
                "## 다른 섹션",
                "- [ ] ignored",
            ]
        ),
    )
    checklist = state.get_plan_checklist(plan)
    assert checklist.completed == 1
    assert checklist.remaining == 2
    assert checklist.total == 3
    assert "step-2" in (checklist.next_task_label or "")


def test_build_status_validates_active_work_pointer(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plans" / "p.md"
    write(plan, "## Step 트리\n- [ ] **step-1** work\n")
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": "w1",
                "works": {
                    "w1": {
                        "work_id": "w1",
                        "status": "active",
                        "plan_path": "docs/plans/p.md",
                        "next_step": "step-1",
                        "execution_mode": "continuous",
                        "approval": {"approved_by": "user", "approved_at": "2026-07-13", "plan_sha256": state.file_sha256(plan)},
                    }
                },
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "pass", report
    assert report["checklist"]["remaining"] == 1


def test_build_status_passes_idle_when_local_state_is_missing(tmp_path: Path) -> None:
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "pass"
    assert report["active_work"] is None
    assert report["checks"][0]["name"] == "state_file"
    assert report["checks"][0]["detail"]["initialized"] is False


def test_build_status_fails_when_local_state_is_invalid(tmp_path: Path) -> None:
    write(tmp_path / ".harness" / "work.json", "{not-json")

    report = state.build_status(tmp_path)

    assert report["summary"]["status"] == "fail"
    assert report["checks"][0]["detail"]["initialized"] is True


def test_next_step_mismatch_is_warn_not_fail(tmp_path: Path) -> None:
    plan = tmp_path / "docs" / "plans" / "p.md"
    write(plan, "## Step 트리\n- [ ] **step-2** work\n")
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": "w1",
                "works": {
                    "w1": {
                        "work_id": "w1",
                        "status": "active",
                        "plan_path": "docs/plans/p.md",
                        "next_step": "step-1",
                        "execution_mode": "continuous",
                        "approval": {"approved_by": "user", "approved_at": "2026-07-13", "plan_sha256": state.file_sha256(plan)},
                    }
                },
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "warn"
    assert any(check["name"] == "next_step_hint" and check["status"] == "warn" for check in report["checks"])


def test_idle_all_terminal_works_passes(tmp_path: Path) -> None:
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": None,
                "works": {
                    "M1-done": {"work_id": "M1-done", "status": "completed"},
                    "M2-abandoned": {"work_id": "M2-abandoned", "status": "abandoned"},
                },
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "pass", report
    active_check = next(c for c in report["checks"] if c["name"] == "active_work")
    assert active_check["status"] == "pass"
    assert "idle" in active_check["message"]


def test_dangling_active_work_pointer_fails(tmp_path: Path) -> None:
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": "does-not-exist",
                "works": {"M1-done": {"work_id": "M1-done", "status": "completed"}},
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "fail", report
    active_check = next(c for c in report["checks"] if c["name"] == "active_work")
    assert active_check["status"] == "fail"


def test_non_terminal_work_without_active_pointer_fails(tmp_path: Path) -> None:
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": None,
                "works": {
                    "M1-done": {"work_id": "M1-done", "status": "completed"},
                    "M2-active": {"work_id": "M2-active", "status": "active"},
                },
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "fail", report
    active_check = next(c for c in report["checks"] if c["name"] == "active_work")
    assert active_check["status"] == "fail"


def test_active_work_without_approval_receipt_fails(tmp_path: Path) -> None:
    write(tmp_path / "docs" / "plans" / "p.md", "## Step 트리\n- [ ] **step-1** work\n")
    write(
        tmp_path / ".harness" / "work.json",
        json.dumps(
            {
                "schema_version": 1,
                "active_work_id": "w1",
                "works": {"w1": {"work_id": "w1", "status": "active", "plan_path": "docs/plans/p.md"}},
            }
        ),
    )
    report = state.build_status(tmp_path)
    assert report["summary"]["status"] == "fail"
    assert any(check["name"] == "approval_receipt" and check["status"] == "fail" for check in report["checks"])


PLAN_BODY = """# PLAN — x

## Step 트리

- [ ] **step-1 — 첫 작업**
  - Verify: cmd
- [ ] **step-2 — 둘째 작업**
  - Verify: cmd
"""


def _approved_work(plan: Path, digest: str) -> dict:
    return {
        "execution_mode": "continuous",
        "approval": {"approved_by": "user", "approved_at": "2026-07-21", "plan_sha256": digest},
    }


# MM7 step-1 (2026-07-21): 승인 후 step 체크박스를 켜는 건 정상 진행이다.
# 이걸 변조로 잡으면 continuation 이 차단된다(skill-sweep·MM3 에서 각각 재현됨).
def test_checkbox_toggle_does_not_break_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)

    plan.write_text(PLAN_BODY.replace("- [ ] **step-1", "- [x] **step-1"), encoding="utf-8")
    assert state.approval_errors(_approved_work(plan, digest), plan) == []


def test_checkbox_line_text_change_still_breaks_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)

    plan.write_text(PLAN_BODY.replace("첫 작업", "전혀 다른 작업"), encoding="utf-8")
    errors = state.approval_errors(_approved_work(plan, digest), plan)
    assert any("hash does not match" in e for e in errors)


# 2026-08-06 감사 #2: 계획서가 사라진 영수증이 승인 통과하던 구멍. 해시 후보가 비면
# 비교를 건너뛰던 자리를 fail-closed 로 바꿨다.
def test_missing_plan_file_breaks_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)
    assert state.approval_errors(_approved_work(plan, digest), plan) == []

    plan.unlink()
    errors = state.approval_errors(_approved_work(plan, digest), plan)
    assert any("unreadable or missing" in e for e in errors)


def test_body_change_outside_checkboxes_still_breaks_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)

    plan.write_text(PLAN_BODY.replace("Verify: cmd", "Verify: 아무거나"), encoding="utf-8")
    errors = state.approval_errors(_approved_work(plan, digest), plan)
    assert any("hash does not match" in e for e in errors)


def test_legacy_raw_file_hash_is_still_accepted(tmp_path):
    """MM7 이전에 바인딩된 승인은 재승인 없이 계속 쓸 수 있어야 한다."""
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    legacy = state.file_sha256(plan)
    assert state.approval_errors(_approved_work(plan, legacy), plan) == []


# MM7 step-3 (2026-07-21): 승인 없이 §E 로 들어간 상태와 milestone 사이의 정상 유휴가
# `status` 에서 둘 다 PASS 0/0 으로 보여 "승인을 안 받았다"가 침묵했다(HQ1 finding).
def _state_file(tmp_path: Path, payload: dict) -> Path:
    (tmp_path / ".harness").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".harness" / "work.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_require_approval_rejects_when_no_active_work(tmp_path):
    root = _state_file(tmp_path, {"schema_version": 1, "active_work_id": None, "works": {}})
    ok, message = state.require_approval(root)
    assert ok is False
    assert "승인된 active work 가 없다" in message


def test_require_approval_rejects_when_receipt_is_broken(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    root = _state_file(
        tmp_path,
        {
            "schema_version": 1,
            "active_work_id": "W1",
            "works": {
                "W1": {
                    "work_id": "W1",
                    "status": "active",
                    "plan_path": "plan.md",
                    "execution_mode": "continuous",
                    "approval": {
                        "approved_by": "user",
                        "approved_at": "2026-07-21",
                        "plan_sha256": "0" * 64,
                    },
                }
            },
        },
    )
    ok, message = state.require_approval(root)
    assert ok is False
    assert "승인 영수증이 성립하지 않는다" in message


def test_require_approval_accepts_valid_receipt(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    root = _state_file(
        tmp_path,
        {
            "schema_version": 1,
            "active_work_id": "W1",
            "works": {
                "W1": {
                    "work_id": "W1",
                    "status": "active",
                    "plan_path": "plan.md",
                    "execution_mode": "continuous",
                    "approval": {
                        "approved_by": "user",
                        "approved_at": "2026-07-21",
                        "plan_sha256": state.plan_fingerprint(plan),
                    },
                }
            },
        },
    )
    ok, message = state.require_approval(root)
    assert ok is True
    assert "승인 확인" in message


def test_require_approval_accepts_after_checkbox_toggle(tmp_path):
    """정상 진행(체크박스 켜기) 후에도 게이트가 오발화하지 않아야 한다."""
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)
    plan.write_text(PLAN_BODY.replace("- [ ] **step-1", "- [x] **step-1"), encoding="utf-8")
    root = _state_file(
        tmp_path,
        {
            "schema_version": 1,
            "active_work_id": "W1",
            "works": {
                "W1": {
                    "work_id": "W1",
                    "status": "active",
                    "plan_path": "plan.md",
                    "execution_mode": "continuous",
                    "approval": {
                        "approved_by": "user",
                        "approved_at": "2026-07-21",
                        "plan_sha256": digest,
                    },
                }
            },
        },
    )
    ok, _ = state.require_approval(root)
    assert ok is True


# CF3 step-3 (2026-07-21): 봉인 대상은 계획의 **내용**이지 표현이 아니다.
# `.gitattributes` 대량 정규화가 승인을 깨 continuation 이 막힌 실사고가 이틀 이월됐다.
def test_line_ending_change_does_not_break_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_bytes(PLAN_BODY.encode("utf-8"))
    digest = state.plan_fingerprint(plan)

    plan.write_bytes(PLAN_BODY.replace("\n", "\r\n").encode("utf-8"))
    assert state.approval_errors(_approved_work(plan, digest), plan) == []


def test_trailing_whitespace_does_not_break_approval(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)

    padded = "\n".join(line + "   " for line in PLAN_BODY.split("\n"))
    plan.write_text(padded, encoding="utf-8")
    assert state.approval_errors(_approved_work(plan, digest), plan) == []


def test_representation_tolerance_does_not_weaken_tamper_detection(tmp_path):
    """관용이 검출력까지 풀어버리면 승인이 무의미해진다 — 표현+내용 동시 변경도 잡는다."""
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)

    tampered = PLAN_BODY.replace("Verify: cmd", "Verify: 아무거나")
    plan.write_bytes("\n".join(l + "  " for l in tampered.split("\n")).replace("\n", "\r\n").encode("utf-8"))
    errors = state.approval_errors(_approved_work(plan, digest), plan)
    assert any("hash does not match" in e for e in errors)


def test_normalizer_matches_the_approver_side(tmp_path):
    """작성자(custom-skills approve_harness_plan.py)와 검증자의 정규화는 반드시 같다.

    둘이 갈리면 승인 직후부터 hash 가 안 맞아 continuation 이 상시 차단된다.
    """
    approver = (
        Path.home() / "projects" / "custom-skills" / "promoted" / "harness-run" / "scripts"
        / "approve_harness_plan.py"
    )
    if not approver.is_file():
        pytest.skip("custom-skills 체크아웃 없음")
    import importlib.util

    spec = importlib.util.spec_from_file_location("_approver", approver)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sample = PLAN_BODY.replace("\n", "\r\n") + "  \n\n"
    assert mod.normalize_plan_text(sample) == state.normalize_plan_text(sample)


# CF6 (2026-07-22): step 진행 상태의 소스가 둘(plan 체크박스 / work.json steps)인데
# steps 를 갱신하는 경로가 approve 와 report_close 뿐이라 중간 진행이 기록되지 않았다.
# Stop hook 이 steps 를 읽으므로 milestone 절반을 끝내도 "next: step-1" 로 보고했다.
def _work_with_steps():
    return {"steps": [
        {"id": "step-1", "label": "step-1 — 첫 작업", "status": "pending"},
        {"id": "step-2", "label": "step-2 — 둘째 작업", "status": "pending"},
    ]}


def test_sync_steps_marks_checked_plan_boxes(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [x] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    assert state.sync_steps_from_plan(work, plan) == 1
    assert [s["status"] for s in work["steps"]] == ["completed", "pending"]


def test_sync_steps_is_idempotent(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [x] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    state.sync_steps_from_plan(work, plan)
    assert state.sync_steps_from_plan(work, plan) == 0


def test_runtime_checklist_reflects_synced_steps(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [x] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    state.sync_steps_from_plan(work, plan)
    cl = state.get_runtime_checklist(work, plan)
    assert (cl.completed, cl.remaining) == (1, 1)
    assert cl.next_task_label.startswith("step-2")


def test_resolve_repo_path_follows_plan_into_archive(tmp_path: Path) -> None:
    """완료 plan 이 archive/ 로 옮겨져도 plan_path 가 끊기지 않는다."""
    write(tmp_path / "archive" / "plans" / "p.md", "# plan\n")
    resolved = state.resolve_repo_path(tmp_path, "plans/p.md")
    assert resolved == (tmp_path / "archive" / "plans" / "p.md").resolve()

    write(tmp_path / "plans" / "horizons" / "h.md", "# horizon\n")
    resolved_horizon = state.resolve_repo_path(tmp_path, "archive/horizons/h.md")
    assert resolved_horizon == (tmp_path / "plans" / "horizons" / "h.md").resolve()


def test_resolve_repo_path_does_not_swallow_absence(tmp_path: Path) -> None:
    """양쪽 다 없으면 폴백이 부재를 가리지 않고 원래 경로를 돌려준다."""
    resolved = state.resolve_repo_path(tmp_path, "plans/missing.md")
    assert resolved == (tmp_path / "plans" / "missing.md").resolve()
    assert not resolved.exists()


def test_resolve_repo_path_prefers_live_path_when_both_exist(tmp_path: Path) -> None:
    write(tmp_path / "plans" / "p.md", "# live\n")
    write(tmp_path / "archive" / "plans" / "p.md", "# archived\n")
    resolved = state.resolve_repo_path(tmp_path, "plans/p.md")
    assert resolved == (tmp_path / "plans" / "p.md").resolve()


def test_plan_fingerprint_survives_eol_normalization(tmp_path: Path) -> None:
    """줄바꿈 정규화가 승인 바인딩을 깨지 않는다 (2026-07-21 사고 종결).

    EOL 규칙 도입이 승인된 plan 의 *바이트*를 바꿔 continuation 을 막았던 건이
    있다. 계약은 "표현은 흡수하고 내용은 봉인" 이므로 양방향으로 고정한다.
    """
    body = "# PLAN — x\n\n- [ ] **step-1 — a**\n  - Verify: cmd\n"
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    trailing = tmp_path / "trailing.md"
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    trailing.write_bytes(body.replace("\n", "   \n").encode("utf-8"))

    baseline = state.plan_fingerprint(lf)
    assert state.plan_fingerprint(crlf) == baseline
    assert state.plan_fingerprint(trailing) == baseline

    changed = tmp_path / "changed.md"
    changed.write_bytes(body.replace("Verify: cmd", "Verify: other").encode("utf-8"))
    assert state.plan_fingerprint(changed) != baseline


def test_approval_errors_accept_normalized_receipt_and_reject_edits(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_bytes("# PLAN — x\r\n\r\n- [ ] **step-1 — a**\r\n".encode("utf-8"))
    work = {
        "execution_mode": "continuous",
        "approval": {
            "approved_by": "user",
            "approved_at": "2026-07-22",
            "plan_sha256": state.plan_fingerprint(plan),
        },
    }
    assert state.approval_errors(work, plan) == []

    plan.write_bytes("# PLAN — x\n\n- [ ] **step-1 — b**\n".encode("utf-8"))
    assert any("hash does not match" in e for e in state.approval_errors(work, plan))


# 2026-07-22 사용자 확정: 계획서는 에이전트가 자기 진행을 체크·기록하는 장부다.
# 따라서 체크박스가 진행의 원본이고 work.json steps[] 는 승인 때 박힌 명단일 뿐이다.
def test_runtime_checklist_derives_from_plan_without_manual_sync(tmp_path):
    """손으로 sync 를 부르지 않아도 plan 체크박스가 그대로 반영된다."""
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [x] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()  # steps[] 는 전부 pending 인 채 — 동기화 안 된 상태
    cl = state.get_runtime_checklist(work, plan)
    assert (cl.completed, cl.remaining) == (1, 1)
    assert cl.next_task_label.startswith("step-2")


def test_completed_work_does_not_report_a_next_step(tmp_path):
    """오늘 실측한 어긋남의 회귀: 계획서가 3/3 인데 'next: step-2' 라고 말하던 상태."""
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [x] **step-1 — 첫 작업**\n- [x] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    cl = state.get_runtime_checklist(work, plan)
    assert (cl.completed, cl.remaining) == (2, 0)
    assert cl.next_task_label is None


def test_stale_completed_status_is_corrected_downward(tmp_path):
    """steps[] 가 completed 라고 우겨도 plan 체크박스가 비었으면 미완이다 — plan 이 원본."""
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [ ] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    work["steps"][0]["status"] = "completed"
    cl = state.get_runtime_checklist(work, plan)
    assert (cl.completed, cl.remaining) == (0, 2)


def test_blocked_status_survives_plan_derivation(tmp_path):
    """blocked·error 는 체크박스가 표현 못 하는 정보라 파생이 덮지 않는다."""
    plan = tmp_path / "plan.md"
    plan.write_text("## Step 트리\n- [ ] **step-1 — 첫 작업**\n- [ ] **step-2 — 둘째 작업**\n", encoding="utf-8")
    work = _work_with_steps()
    work["steps"][0]["status"] = "blocked"
    state.get_runtime_checklist(work, plan)
    assert work["steps"][0]["status"] == "blocked"


# 2026-07-22: 계획서가 에이전트의 진행 장부라면, 실행 중 finding·진행 로그를 적는 것은
# 정상 동작이다. 승인 해시가 그걸 변조로 잡으면 템플릿과 게이트가 서로를 부정한다.
_LEDGER_BASE = """## 검증/DoD
- DoD: 무언가

## finding 큐
- (비어 있음)

## 진행 로그 (append-only)
- 2026-07-22 계획 작성
"""


def test_append_only_sections_do_not_break_approval(tmp_path):
    written = _LEDGER_BASE.replace("- (비어 있음)", "- F1 실행 중 발견한 것").replace(
        "- 2026-07-22 계획 작성", "- 2026-07-22 계획 작성\n- 2026-07-22 step-1 완료"
    )
    assert state.normalize_plan_text(_LEDGER_BASE) == state.normalize_plan_text(written)


def test_body_outside_append_only_is_still_sealed(tmp_path):
    tampered = _LEDGER_BASE.replace("- DoD: 무언가", "- DoD: 슬쩍 바꾼 것")
    assert state.normalize_plan_text(_LEDGER_BASE) != state.normalize_plan_text(tampered)


def test_removing_or_renaming_an_append_only_section_is_detected(tmp_path):
    renamed = _LEDGER_BASE.replace("## finding 큐", "## 발견")
    removed = _LEDGER_BASE.replace("## finding 큐\n- (비어 있음)\n\n", "")
    base = state.normalize_plan_text(_LEDGER_BASE)
    assert base != state.normalize_plan_text(renamed)
    assert base != state.normalize_plan_text(removed)


# ── OI2 step-4: 다음 leaf 를 텍스트 순서가 아니라 그래프에서 ────────────────────
def _plan_file(tmp_path, body: str):
    p = tmp_path / "plan.md"
    p.write_text("## Step 트리\n" + body, encoding="utf-8")
    return p


def test_ready_leaves_are_derived_from_dependencies(tmp_path):
    p = _plan_file(tmp_path,
        "- [ ] **step-1 — a**\n  - Files: `a.py`\n  - Dependencies: none\n"
        "- [ ] **step-2 — b**\n  - Files: `b.py`\n  - Dependencies: none\n"
        "- [ ] **step-3 — c**\n  - Files: `c.py`\n  - Dependencies: step-1, step-2\n")
    c = state.get_plan_checklist(p)
    assert set(c.ready_labels) == {"step-1 — a", "step-2 — b"}
    assert "step-3" not in " ".join(c.ready_labels)


def test_completed_leaves_unlock_the_next_wave(tmp_path):
    p = _plan_file(tmp_path,
        "- [x] **step-1 — a**\n  - Files: `a.py`\n  - Dependencies: none\n"
        "- [x] **step-2 — b**\n  - Files: `b.py`\n  - Dependencies: none\n"
        "- [ ] **step-3 — c**\n  - Files: `c.py`\n  - Dependencies: step-1, step-2\n")
    c = state.get_plan_checklist(p)
    assert c.ready_labels == ("step-3 — c",)
    assert c.next_task_label == "step-3 — c"


def test_unsatisfied_dependency_is_never_offered_as_next(tmp_path):
    p = _plan_file(tmp_path,
        "- [ ] **step-1 — a**\n  - Files: `a.py`\n  - Dependencies: none\n"
        "- [ ] **step-2 — b**\n  - Files: `b.py`\n  - Dependencies: step-1\n")
    c = state.get_plan_checklist(p)
    assert c.ready_labels == ("step-1 — a",)


def test_cycle_falls_back_to_text_order_without_hanging(tmp_path):
    """검증기를 우회해 들어온 순환도 무한 대기·조용한 통과가 아니라 명시적 폴백."""
    p = _plan_file(tmp_path,
        "- [ ] **step-1 — a**\n  - Dependencies: step-2\n"
        "- [ ] **step-2 — b**\n  - Dependencies: step-1\n")
    c = state.get_plan_checklist(p)
    assert c.ready_labels == ()
    assert c.next_task_label == "**step-1 — a**"   # 텍스트 순서 폴백


def test_legacy_plan_without_dependencies_still_works(tmp_path):
    """의존 줄이 없는 구 plan(실측 116 step)은 그대로 동작해야 한다."""
    p = _plan_file(tmp_path, "- [ ] **step-1 — a**\n- [ ] **step-2 — b**\n")
    c = state.get_plan_checklist(p)
    assert c.remaining == 2 and c.next_task_label


# ── OI3 실행 장애 수리: 연쇄 진행을 훅 발화 횟수에 의존시키지 않는다 ──────────
def test_next_chained_command_reports_next_milestone(tmp_path, monkeypatch, capsys):
    """완료 절차가 직접 물을 수 있어야 한다 — 훅은 milestone 을 한 개만 더 밀어준다."""
    (tmp_path / ".harness").mkdir()
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "2026-07-23-m2-slug.md").write_text(
        "# PLAN\n> horizon: h1\n", encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text(
        '<!-- harness:goal id="h1" -->\n목표: x\n'
        '<!-- harness:milestone id="M1" status="completed" -->\n'
        '<!-- harness:milestone id="M2" status="pending" -->\n'
        "- Plan: `plans/p2.md`\n",
        encoding="utf-8")
    (tmp_path / ".harness" / "work.json").write_text(json.dumps({
        "active_work_id": "w1",
        "works": {"w1": {"work_id": "w1", "status": "completed",
                          "horizon_id": "h1", "milestone_id": "M1",
                          "plan_path": "plans/2026-07-23-m2-slug.md",
                          # FA1: 연쇄는 승인 이력이 있어야 후보다 — 승인 게이트에서
                          # 제시·승인된 목록이 chain 으로 기록된 정상 케이스.
                          "approval": {"plan_sha256": "sealed", "chain": ["M2"]}}},
    }), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path)])
    assert state.main() == 0
    out = capsys.readouterr().out
    assert "M2" in out and "2026-07-23-m2-slug.md" in out


# ── FA1 step-1 (2026-07-24): 연쇄 자기승인 구멍 봉쇄 ─────────────────────────
def _chain_repo(tmp_path, work_extra=None, extra_works=None):
    """pending M2 + 살아있는 plan 을 가진 최소 레포. 승인 기록은 인자로 주입."""
    (tmp_path / ".harness").mkdir()
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "2026-07-24-m2-slug.md").write_text("# PLAN\n", encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text(
        '<!-- harness:milestone id="M1" status="completed" -->\n'
        '<!-- harness:milestone id="M2" status="pending" -->\n',
        encoding="utf-8")
    w1 = {"work_id": "w1", "status": "completed", "milestone_id": "M1"}
    w1.update(work_extra or {})
    works = {"w1": w1}
    works.update(extra_works or {})
    (tmp_path / ".harness" / "work.json").write_text(
        json.dumps({"active_work_id": "w1", "works": works}), encoding="utf-8")


def test_next_chained_rejects_unapproved_draft(tmp_path, monkeypatch, capsys):
    """계획서가 plans/ 에 있다 ≠ 승인됐다 — 미승인 초안은 연쇄 후보가 아니다."""
    _chain_repo(tmp_path, work_extra={"approval": {"plan_sha256": "sealed"}})
    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path)])
    assert state.main() == 1
    out = capsys.readouterr().out
    assert "남은 milestone 없음" in out
    assert "미승인 후보" in out and "M2" in out


def test_next_chained_accepts_chain_recorded_at_approval(tmp_path, monkeypatch, capsys):
    """승인 게이트에서 --chain 으로 기록된 후속 milestone 은 무개입 연쇄 대상이다."""
    _chain_repo(tmp_path, work_extra={"approval": {"plan_sha256": "sealed", "chain": ["m2"]}})
    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path)])
    assert state.main() == 0
    assert "M2" in capsys.readouterr().out


def test_next_chained_accepts_milestone_with_own_receipt(tmp_path, monkeypatch, capsys):
    """해당 계획 자체가 approve 로 등록돼 있으면(자체 영수증) 승인 이력으로 인정한다."""
    _chain_repo(
        tmp_path,
        work_extra={"approval": {"plan_sha256": "sealed"}},
        extra_works={"w2": {"work_id": "w2", "status": "paused", "milestone_id": "M2",
                             "approval": {"plan_sha256": "sealed-2"}}},
    )
    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path)])
    assert state.main() == 0
    assert "M2" in capsys.readouterr().out


def test_next_chained_exits_nonzero_when_chain_is_done(tmp_path, monkeypatch, capsys):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "ROADMAP.md").write_text(
        '<!-- harness:goal id="h1" -->\n'
        '<!-- harness:milestone id="M1" status="completed" -->\n', encoding="utf-8")
    (tmp_path / ".harness" / "work.json").write_text(json.dumps({
        "active_work_id": "w1",
        "works": {"w1": {"work_id": "w1", "status": "completed",
                          "horizon_id": "h1", "milestone_id": "M1"}},
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path)])
    assert state.main() == 1
    assert "남은 milestone 없음" in capsys.readouterr().out


# ── M9 step-1 (2026-09-02): 같은 회차의 승인 다수 ──────────────────────────
# 계획 2본을 승인하면 두 번째 등록이 포인터를 덮어 첫 승인의 훅·continuation 이
# 침묵했다. 포인터 의미는 그대로 두고(D1) 승인 다수는 continuable 집합으로 표현한다.
def _multi_work_state(tmp_path: Path, pointer: str | None = "wA") -> tuple[Path, Path, Path]:
    plan_a = tmp_path / "plans" / "a.md"
    plan_b = tmp_path / "plans" / "b.md"
    write(plan_a, PLAN_BODY)
    write(plan_b, PLAN_BODY.replace("첫 작업", "B 첫 작업"))
    payload = {
        "schema_version": 1,
        "active_work_id": pointer,
        "works": {
            "wA": {
                "work_id": "wA",
                "status": "active",
                "plan_path": "plans/a.md",
                "owner_session_uuid": "claude:aaa",
                "session_ids": ["claude:aaa"],
                "execution_mode": "continuous",
                "approval": {
                    "approved_by": "user",
                    "approved_at": "2026-09-02",
                    "plan_sha256": state.plan_fingerprint(plan_a),
                },
            },
            "wB": {
                "work_id": "wB",
                "status": "active",
                "plan_path": "plans/b.md",
                "owner_session_uuid": "claude:bbb",
                "session_ids": ["claude:bbb"],
                "execution_mode": "continuous",
                "approval": {
                    "approved_by": "user",
                    "approved_at": "2026-09-02",
                    "plan_sha256": state.plan_fingerprint(plan_b),
                },
            },
        },
    }
    return _state_file(tmp_path, payload), plan_a, plan_b


def test_session_work_prefers_owned_work_over_the_pointer(tmp_path: Path) -> None:
    root, _, _ = _multi_work_state(tmp_path, pointer="wA")
    payload = json.loads((root / ".harness" / "work.json").read_text(encoding="utf-8"))
    # 소유가 포인터를 이긴다 — 안 그러면 비소유 세션이 남의 영수증으로 통과한다(B6).
    assert state.session_work(payload, "claude:bbb")["work_id"] == "wB"
    assert state.session_work(payload, "claude:aaa")["work_id"] == "wA"
    # 소유가 판정 안 되면 포인터로 떨어진다.
    assert state.session_work(payload, "claude:zzz")["work_id"] == "wA"
    payload["active_work_id"] = None
    assert state.session_work(payload, "claude:bbb")["work_id"] == "wB"
    assert state.session_work(payload, None) is None
    assert {w["work_id"] for w in state.continuable_works(payload)} == {"wA", "wB"}


def test_session_work_falls_back_to_the_only_continuable(tmp_path: Path) -> None:
    root, _, _ = _multi_work_state(tmp_path, pointer="wDone")
    payload = json.loads((root / ".harness" / "work.json").read_text(encoding="utf-8"))
    payload["works"]["wDone"] = {"work_id": "wDone", "status": "completed"}
    del payload["works"]["wB"]
    assert state.session_work(payload, None)["work_id"] == "wA"


def test_resume_moves_the_pointer_and_leaves_the_other_work_intact(tmp_path: Path) -> None:
    root, _, _ = _multi_work_state(tmp_path, pointer="wA")
    before = json.loads((root / ".harness" / "work.json").read_text(encoding="utf-8"))["works"]["wA"]
    ok, message = state.resume_work(root, "wB", "claude:ccc")
    assert ok, message
    after = json.loads((root / ".harness" / "work.json").read_text(encoding="utf-8"))
    assert after["active_work_id"] == "wB"
    assert after["works"]["wB"]["owner_session_uuid"] == "claude:ccc"
    assert after["works"]["wA"] == before


def test_require_approval_does_not_pass_on_another_works_receipt(tmp_path: Path) -> None:
    """포인터가 A 를 가리켜도 B 세션은 B 의 영수증으로 판정받는다 (리뷰 지적 1)."""
    root, plan_a, plan_b = _multi_work_state(tmp_path, pointer="wA")
    assert state.require_approval(root, token="claude:bbb")[1].endswith("plans/b.md")
    plan_b.write_text(PLAN_BODY.replace("첫 작업", "변조"), encoding="utf-8")
    ok, message = state.require_approval(root, token="claude:bbb")
    assert ok is False, message
    # A 세션은 자기 영수증으로 계속 통과한다.
    assert state.require_approval(root, token="claude:aaa")[0] is True


def test_require_approval_judges_the_session_work_and_work_id_wins(tmp_path: Path) -> None:
    root, plan_a, plan_b = _multi_work_state(tmp_path, pointer=None)
    ok, message = state.require_approval(root, token="claude:bbb")
    assert ok and "wB" in message
    # --work-id 명시가 세션 선택을 이긴다.
    ok, message = state.require_approval(root, token="claude:bbb", work_id="wA")
    assert ok and "wA" in message
    # 다른 work 의 영수증으로 통과하지 않는다: B 의 계획서를 변조하면 B 만 거부된다.
    plan_b.write_text(PLAN_BODY.replace("첫 작업", "변조"), encoding="utf-8")
    ok, message = state.require_approval(root, token="claude:bbb")
    assert ok is False and "영수증이 성립하지 않는다" in message
    assert state.require_approval(root, token="claude:bbb", work_id="wA")[0] is True


def test_completed_pointer_regression_is_unchanged(tmp_path: Path) -> None:
    """B1 회귀 고정 — 포인터가 completed 인 레포에서 판정이 착수와 같아야 한다."""
    (tmp_path / ".harness").mkdir()
    (tmp_path / "plans").mkdir()
    write(tmp_path / "plans" / "2026-09-02-m2-slug.md", "# PLAN\n")
    (tmp_path / "ROADMAP.md").write_text(
        '<!-- harness:goal id="h1" -->\n'
        '<!-- harness:milestone id="M1" status="completed" -->\n'
        '<!-- harness:milestone id="M2" status="pending" -->\n'
        "- Plan: `plans/p2.md`\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": 1,
        "active_work_id": "w1",
        "works": {
            "w1": {
                "work_id": "w1",
                "status": "completed",
                "horizon_id": "h1",
                "milestone_id": "M1",
                "plan_path": "plans/2026-09-02-m2-slug.md",
                "approval": {"plan_sha256": "sealed", "chain": ["M2"]},
            }
        },
    }
    (tmp_path / ".harness" / "work.json").write_text(json.dumps(payload), encoding="utf-8")
    assert state.active_work(payload)["work_id"] == "w1"
    report = state.build_status(tmp_path)
    # 완료 포인터에서 `fail: active work does not resolve` 로 뒤집히지 않는다(B1 probe).
    assert report["summary"]["status"] != "fail"
    assert [c["status"] for c in report["checks"] if c["name"] == "active_work"] == ["pass"]
    chained = state.next_chained_milestone(tmp_path, payload["works"]["w1"], payload)
    assert chained and chained["milestone_id"] == "M2"
    # 완료 포인터는 continuable 집합에 들지 않는다.
    assert state.continuable_works(payload) == []


# ── M9 step-4 (2026-09-02): 승인 대조는 기계가 한 줄로 낸다 ──────────────────
# raw sha256 손대조는 CRLF 체크아웃에서 반드시 어긋난다 — 그 오경보로 4수를 낭비한
# 사고가 있었다. 판정은 approval_errors 와 같은 후보 집합을 쓴다(새 해시 경로 없음).
def _verdict_repo(tmp_path: Path, digest: str, newline: str = "\n") -> dict:
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY.replace("\n", newline), encoding="utf-8", newline="")
    return {
        "work_id": "w1",
        "status": "active",
        "plan_path": "plan.md",
        "execution_mode": "continuous",
        "approval": {"approved_by": "user", "approved_at": "2026-09-02", "plan_sha256": digest},
    }


def test_approval_verdict_reports_normalized_match_on_crlf(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)
    work = _verdict_repo(tmp_path, digest, newline="\r\n")
    assert state.approval_verdict(tmp_path, work) == f"정규화 일치({digest[:8]})"


def test_approval_verdict_reports_legacy_raw_match(tmp_path: Path) -> None:
    # CRLF 로 저장해 raw 해시와 정규화 해시가 실제로 갈리게 한다(LF 파일에서는 같다).
    work = _verdict_repo(tmp_path, "placeholder", newline="\r\n")
    # MM7 이전 승인은 raw 파일 해시로 바인딩됐다 — 재승인 없이 계속 읽혀야 한다.
    work["approval"]["plan_sha256"] = state.file_sha256(tmp_path / "plan.md")
    assert state.approval_verdict(tmp_path, work) == "legacy raw 일치"


def test_approval_verdict_detects_a_body_edit(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    digest = state.plan_fingerprint(plan)
    work = _verdict_repo(tmp_path, digest)
    plan.write_text(PLAN_BODY.replace("첫 작업", "전혀 다른 작업"), encoding="utf-8")
    assert state.approval_verdict(tmp_path, work) == "불일치"


def test_approval_verdict_reports_a_missing_plan(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_BODY, encoding="utf-8")
    work = _verdict_repo(tmp_path, state.plan_fingerprint(plan))
    plan.unlink()
    assert state.approval_verdict(tmp_path, work) == "계획서 없음"


def test_diagnose_lists_continuable_works_with_approval_lines(tmp_path: Path) -> None:
    root, _, _ = _multi_work_state(tmp_path, pointer="wA")
    verdict = state.diagnose(root, "claude:aaa")
    assert verdict["approvals"][0] == "continuable: [wA, wB]"
    assert any(line.startswith("  wA approval: 정규화 일치(") for line in verdict["approvals"])
    assert any(line.startswith("  wB approval: 정규화 일치(") for line in verdict["approvals"])


def test_diagnose_carries_approvals_on_the_not_owner_branch(tmp_path: Path) -> None:
    """이어받는 세션이 가장 먼저 보는 분기다 — 여기가 비면 대조를 할 수 없다 (리뷰 지적 3)."""
    root, _, _ = _multi_work_state(tmp_path, pointer="wA")
    verdict = state.diagnose(root, "claude:zzz")
    assert verdict["reason"] == "not-owner"
    assert verdict["approvals"][0] == "continuable: [wA, wB]"
    assert any("approval: 정규화 일치(" in line for line in verdict["approvals"])


# M23 step-1 (2026-10-26): 목표 chain 에 든 다음 milestone 에 계획서가 아직 없으면
# 「멈춤」(exit 1) 이 아니라 「계획 필요」(exit 3) — 끝난 세션이 계획을 쓰고 이어간다.
ROADMAP_GOAL = """# Roadmap
<!-- harness:milestone id="M1" status="completed" -->
### M1 — first
- DoD: one done
<!-- harness:milestone id="M2" status="pending" -->
### M2 — second
- DoD: two done
<!-- harness:milestone id="M3" status="pending" -->
### M3 — third
- DoD: three done
"""


def _goal_state(tmp_path: Path) -> None:
    write(tmp_path / "ROADMAP.md", ROADMAP_GOAL)
    (tmp_path / "plans").mkdir()
    payload = {
        "schema_version": 1,
        "active_work_id": "W1",
        "works": {
            "W1": {
                "work_id": "W1", "milestone_id": "M1", "status": "completed",
                "approval": {"plan_sha256": "x", "chain": ["M2", "M3"]},
            }
        },
    }
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))


def test_next_chained_needs_plan_for_chain_member_without_plan(tmp_path, monkeypatch, capsys) -> None:
    _goal_state(tmp_path)
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "next-chained", "--root", str(tmp_path), "--json"])
    rc = state.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 3
    assert payload["status"] == "needs-plan"
    assert payload["milestone_id"] == "M2"
    assert payload["dod"] == "two done"


def test_next_chained_ready_when_chain_member_has_plan(tmp_path, monkeypatch, capsys) -> None:
    _goal_state(tmp_path)
    write(tmp_path / "plans" / "2026-10-26-m2-second.md", "# Plan\n")
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "next-chained", "--root", str(tmp_path), "--json"])
    rc = state.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ready"
    assert payload["milestone_id"] == "M2"


def test_resume_triggers_chain_handoff_on_resume(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(state, "resume_work", lambda root, wid, token: (True, "resumed"))
    monkeypatch.setattr(state, "require_approval", lambda root, token, wid, runtime: (True, "PASS"))
    import chain_handoff
    monkeypatch.setattr(chain_handoff, "on_resume", lambda root, wid, **kw: calls.append((root, wid)) or ["started"])
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "resume", "--root", str(tmp_path),
                                      "--work-id", "W1", "--session", "claude:abc"])
    assert state.main() == 0
    assert calls and calls[0][1] == "W1"
    assert "started" in capsys.readouterr().out


def test_resume_withholds_started_when_receipt_mismatches(tmp_path, monkeypatch, capsys) -> None:
    """D8 ③ — 영수증이 어긋나면 started 를 보내지 않는다(예전 세션이 열린 채 남도록)."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(state, "resume_work", lambda root, wid, token: (True, "resumed"))
    monkeypatch.setattr(state, "require_approval", lambda root, token, wid, runtime: (False, "hash does not match"))
    import chain_handoff
    monkeypatch.setattr(chain_handoff, "on_resume", lambda root, wid, **kw: calls.append((root, wid)) or ["started"])
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "resume", "--root", str(tmp_path),
                                      "--work-id", "W1", "--session", "claude:abc"])
    assert state.main() == 1
    assert calls == []
    assert "started 보류" in capsys.readouterr().out


def test_next_chained_exit_1_when_chain_all_done(tmp_path, monkeypatch, capsys) -> None:
    _goal_state(tmp_path)
    text = (tmp_path / "ROADMAP.md").read_text(encoding="utf-8").replace('status="pending"', 'status="completed"')
    write(tmp_path / "ROADMAP.md", text)
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "next-chained", "--root", str(tmp_path), "--json"])
    assert state.main() == 1


def test_next_chained_finds_uppercase_plan_name(tmp_path, monkeypatch, capsys) -> None:
    _goal_state(tmp_path)
    write(tmp_path / "plans" / "2026-10-26-M2-second.md", "# Plan\n")
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "next-chained", "--root", str(tmp_path), "--json"])
    assert state.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


# ── 2026-11-03: next-chained 연쇄 범위 = 방금 닫은 work 가 속한 chain ─────────
ROADMAP_SCOPE = """# Roadmap
<!-- harness:milestone id="M128" status="active" -->
### M128 — other session
- DoD: external
<!-- harness:milestone id="M146" status="completed" -->
### M146 — closed
- DoD: closed
<!-- harness:milestone id="M147" status="pending" -->
### M147 — next
- DoD: next done
<!-- harness:milestone id="M148" status="pending" -->
### M148 — after
- DoD: after done
"""


def _scope_state(tmp_path: Path, m147_done: bool = False) -> dict:
    roadmap = ROADMAP_SCOPE
    if m147_done:
        roadmap = roadmap.replace('id="M147" status="pending"', 'id="M147" status="completed"')
    write(tmp_path / "ROADMAP.md", roadmap)
    write(tmp_path / "plans" / "2026-11-02-m147-next.md", "# Plan\n")
    write(tmp_path / "plans" / "2026-10-20-m128-other.md", "# Plan\n")
    payload = {
        "schema_version": 1,
        "active_work_id": "W128",
        "works": {
            "W128": {"work_id": "W128", "milestone_id": "M128", "status": "active",
                     "approval": {"plan_sha256": "s128"}},
            "W146": {"work_id": "W146", "milestone_id": "M146", "status": "completed",
                     "approval": {"plan_sha256": "s146", "chain": ["M147", "M148"]}},
        },
    }
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))
    return payload


def test_next_chained_prefers_own_chain_over_other_active(tmp_path) -> None:
    payload = _scope_state(tmp_path)
    found, _ = state.chain_next(tmp_path, payload["works"]["W146"], payload)
    assert found is not None
    assert found["status"] == "ready"
    assert found["milestone_id"] == "M147"
    assert found["plan_path"] == "plans/2026-11-02-m147-next.md"


def test_next_chained_needs_plan_for_chain_member(tmp_path) -> None:
    payload = _scope_state(tmp_path, m147_done=True)
    found, _ = state.chain_next(tmp_path, payload["works"]["W146"], payload)
    assert found is not None
    assert found["status"] == "needs-plan"
    assert found["milestone_id"] == "M148"
    assert found["dod"] == "after done"


def test_next_chained_cli_honors_work_id(tmp_path, monkeypatch, capsys) -> None:
    payload = _scope_state(tmp_path)
    # 포인터는 M128 이 아닌 제3의 work — --work-id 를 무시하면 M128 이 ready 로 나온다.
    payload["active_work_id"] = "W130"
    payload["works"]["W130"] = {"work_id": "W130", "milestone_id": "M130", "status": "active",
                                "approval": {"plan_sha256": "s130"}}
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))
    monkeypatch.setattr(sys, "argv", ["harness_work_state.py", "next-chained", "--root", str(tmp_path),
                                      "--work-id", "W146", "--json"])
    rc = state.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ready"
    assert payload["milestone_id"] == "M147"


def test_fallback_skips_milestone_owned_by_active_work(tmp_path) -> None:
    # chain 없는 단독 승인 — 폴백. M128 은 다른 세션의 active work 가 쥐고 있다.
    write(tmp_path / "ROADMAP.md", ROADMAP_SCOPE)
    write(tmp_path / "plans" / "2026-11-02-m128-other.md", "# Plan\n")
    write(tmp_path / "plans" / "2026-11-02-m147-next.md", "# Plan\n")
    payload = {
        "schema_version": 1,
        "active_work_id": "W146",
        "works": {
            "W128": {"work_id": "W128", "milestone_id": "M128", "status": "active",
                     "owner_session_uuid": "claude:other-session",
                     "approval": {"plan_sha256": "s128"}},
            "W146": {"work_id": "W146", "milestone_id": "M146", "status": "completed",
                     "owner_session_uuid": "claude:this-session",
                     "approval": {"plan_sha256": "s146"}},
            "W147": {"work_id": "W147", "milestone_id": "M147", "status": "abandoned",
                     "approval": {"plan_sha256": "s147"}},
            "W148": {"work_id": "W148", "milestone_id": "M148", "status": "paused",
                     "approval": {"plan_sha256": "s148"}},
        },
    }
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))
    found = state.next_chained_milestone(tmp_path, payload["works"]["W146"], payload)
    assert found is None


# ── M24 step-1 (2026-11-03): chain-remaining ────────────────────────────────
def test_chain_remaining_lists_pending_members(tmp_path, monkeypatch, capsys):
    write(tmp_path / "ROADMAP.md", (
        '<!-- harness:milestone id="M1" status="active" -->\n'
        '<!-- harness:milestone id="M2" status="completed" -->\n'
        '<!-- harness:milestone id="M3" status="pending" -->\n'
        '<!-- harness:milestone id="M4" status="pending" -->\n'))
    payload = {"schema_version": 1, "active_work_id": "W1", "works": {
        "W1": {"work_id": "W1", "milestone_id": "M1", "status": "active",
               "approval": {"plan_sha256": "s1", "chain": ["M2", "M3"]}}}}
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))
    monkeypatch.setattr(sys, "argv", ["x", "chain-remaining", "--root", str(tmp_path), "--milestone-id", "M1"])
    assert state.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"milestone_id": "M1", "remaining": ["M3"]}


def test_dropped_is_terminal():
    assert "dropped" in state.TERMINAL_STATUSES


# ── 2026-11-08: next-chained 재발 수리 — 자기 chain 우선·chain 순서·work-id 정규화 ──
def _roadmap(*rows: tuple[str, str]) -> str:
    return "# Roadmap\n" + "".join(
        f'<!-- harness:milestone id="{mid}" status="{status}" -->\n### {mid} — t\n- DoD: {mid} dod\n'
        for mid, status in rows
    )


def test_next_chained_follows_chain_order_not_roadmap_order(tmp_path) -> None:
    """사례 ① (m155-surface-audit): ROADMAP 에서 M145 가 앞서도 chain 순서 M156 이 먼저고,
    계획서 없는 M156 은 needs-plan 이어야 한다 — 뒤 멤버 M145 를 ready 로 건너뛰면 안 된다."""
    write(tmp_path / "ROADMAP.md", _roadmap(
        ("M145", "active"), ("M153", "pending"), ("M154", "pending"),
        ("M155", "completed"), ("M156", "pending"), ("M157", "pending")))
    write(tmp_path / "plans" / "2026-11-01-m145-i18n.md", "# Plan\n")
    payload = {"schema_version": 1, "active_work_id": "w155", "works": {
        "w155": {"work_id": "w155", "milestone_id": "M155", "status": "completed",
                 "approval": {"plan_sha256": "s155", "chain": ["M156", "M153", "M154", "M157", "M145"]}}}}
    found, _ = state.chain_next(tmp_path, payload["works"]["w155"], payload)
    assert found is not None
    assert found["status"] == "needs-plan"
    assert found["milestone_id"] == "M156"
    assert found["dod"] == "M156 dod"


def test_next_chained_own_chain_wins_over_older_chain_containing_done_id(tmp_path) -> None:
    """사례 ② (m156): 닫은 work(M156) 자기 chain M158·M159 만 범위다. M156 을 품은 옛 M155 chain 의
    남의 세션 소유 M145 는 합쳐지지 않는다."""
    write(tmp_path / "ROADMAP.md", _roadmap(
        ("M145", "active"), ("M153", "pending"), ("M156", "completed"),
        ("M158", "pending"), ("M159", "pending")))
    write(tmp_path / "plans" / "2026-11-01-m145-i18n.md", "# Plan\n")
    write(tmp_path / "plans" / "2026-11-08-m158-screens.md", "# Plan\n")
    payload = {"schema_version": 1, "active_work_id": "w156", "works": {
        "w145": {"work_id": "w145", "milestone_id": "M145", "status": "active",
                 "owner_session_uuid": "claude:other", "approval": {"plan_sha256": "s145"}},
        "w155": {"work_id": "w155", "milestone_id": "M155", "status": "completed",
                 "approval": {"plan_sha256": "s155", "chain": ["M156", "M153", "M154", "M157", "M145"]}},
        "w156": {"work_id": "w156", "milestone_id": "M156", "status": "completed",
                 "owner_session_uuid": "claude:me",
                 "approval": {"plan_sha256": "s156", "chain": ["M158", "M159"]}}}}
    assert state.chain_scope(payload, payload["works"]["w156"]) == ["m158", "m159"]
    found, _ = state.chain_next(tmp_path, payload["works"]["w156"], payload)
    assert found == {"status": "ready", "milestone_id": "M158",
                     "plan_path": "plans/2026-11-08-m158-screens.md"}
    assert state.next_chained_milestone(tmp_path, payload["works"]["w156"], payload) == {
        "milestone_id": "M158", "plan_path": "plans/2026-11-08-m158-screens.md"}


def test_chain_scope_falls_back_to_older_chain_tail_only_when_own_chain_empty(tmp_path) -> None:
    """자기 chain 이 비었을 때만 옛 chain 의 done_id **뒤** 멤버로 폴백한다(앞 멤버는 이미 지나간 일).

    폴백은 연쇄로 들어온 work(approved_by=chain:…)에만 돈다(M29) — 그래서 wB 는 chain: 승인이다.
    """
    payload = {"schema_version": 1, "works": {
        "wA": {"work_id": "wA", "milestone_id": "M1", "status": "completed",
               "approval": {"plan_sha256": "a", "chain": ["M9", "M2", "M3", "M4"]}},
        "wB": {"work_id": "wB", "milestone_id": "M2", "status": "completed",
               "approval": {"approved_by": "chain:wA", "plan_sha256": "b"}}}}
    assert state.chain_scope(payload, payload["works"]["wB"]) == ["m3", "m4"]
    # 자기 chain 이 자기 자신뿐이어도 빈 것으로 본다.
    payload["works"]["wB"]["approval"]["chain"] = ["M2"]
    assert state.chain_scope(payload, payload["works"]["wB"]) == ["m3", "m4"]


def test_fallback_tail_skips_member_held_by_other_session(tmp_path) -> None:
    # 폴백 경로를 타려면 wB 가 연쇄 승인(chain:)이어야 한다(M29).
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "pending"), ("M4", "pending")))
    write(tmp_path / "plans" / "2026-11-01-m3-x.md", "# Plan\n")
    write(tmp_path / "plans" / "2026-11-01-m4-y.md", "# Plan\n")
    payload = {"schema_version": 1, "works": {
        "wA": {"work_id": "wA", "milestone_id": "M1", "status": "completed",
               "approval": {"plan_sha256": "a", "chain": ["M2", "M3", "M4"]}},
        "wB": {"work_id": "wB", "milestone_id": "M2", "status": "completed",
               "owner_session_uuid": "claude:me", "approval": {"approved_by": "chain:wA", "plan_sha256": "b"}},
        "wC": {"work_id": "wC", "milestone_id": "M3", "status": "active",
               "owner_session_uuid": "claude:other", "approval": {"plan_sha256": "c"}}}}
    found, _ = state.chain_next(tmp_path, payload["works"]["wB"], payload)
    assert found is not None and found["milestone_id"] == "M4" and found["status"] == "ready"


def test_next_chained_stops_when_own_chain_is_exhausted_instead_of_using_older_chain(tmp_path) -> None:
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"), ("M9", "pending")))
    write(tmp_path / "plans" / "2026-11-01-m9-z.md", "# Plan\n")
    payload = {"schema_version": 1, "works": {
        "wA": {"work_id": "wA", "milestone_id": "M1", "status": "completed",
               "approval": {"plan_sha256": "a", "chain": ["M2", "M9"]}},
        "wB": {"work_id": "wB", "milestone_id": "M2", "status": "completed",
               "approval": {"plan_sha256": "b", "chain": ["M3"]}}}}
    found, _ = state.chain_next(tmp_path, payload["works"]["wB"], payload)
    assert found is None


def _standalone_vs_chained_payload(m3_approval: dict) -> dict:
    return {"schema_version": 1, "active_work_id": "m3", "works": {
        "m1": {"work_id": "m1", "milestone_id": "M1", "status": "completed",
               "approval": {"approved_by": "user", "plan_sha256": "s1", "chain": ["M2", "M3", "M4"]}},
        "m3": {"work_id": "m3", "milestone_id": "M3", "status": "completed", "approval": m3_approval}}}


def test_chain_next_standalone_work_ignores_old_chain(tmp_path, monkeypatch, capsys) -> None:
    """단독 승인 work(자기 chain·chained_from 없음, approved_by=user)는 M1 의 옛 chain 꼬리(M4)를 빌리지 않는다."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "completed"), ("M4", "pending")))
    payload = _standalone_vs_chained_payload({"approved_by": "user", "plan_sha256": "s3"})
    write(tmp_path / ".harness" / "work.json", json.dumps(payload))
    assert state.chain_scope(payload, payload["works"]["m3"]) == []
    found, _ = state.chain_next(tmp_path, payload["works"]["m3"], payload)
    assert found is None
    monkeypatch.setattr(sys, "argv", ["x", "next-chained", "--root", str(tmp_path), "--work-id", "m3", "--json"])
    state.main()
    assert json.loads(capsys.readouterr().out) == {}


@pytest.mark.parametrize("m3_approval", [
    {"plan_sha256": "s3"},                                   # approved_by 없는 옛 영수증
    {"approved_by": "fanout:main-w", "plan_sha256": "s3"},  # 펼친 계획의 갈래
    {"approved_by": "user", "plan_sha256": "s3", "chained_from": ""},
])
def test_chain_next_non_chain_approval_never_falls_back(tmp_path, m3_approval) -> None:
    """chain: 이 아닌 승인은 모두 옛 chain 꼬리를 빌리지 않는다(M29 결정 — 폴백은 연쇄로 들어온 work 만)."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "completed"), ("M4", "pending")))
    payload = _standalone_vs_chained_payload(m3_approval)
    found, _ = state.chain_next(tmp_path, payload["works"]["m3"], payload)
    assert found is None


def test_chain_next_standalone_work_with_next_plan_present_still_stops(tmp_path) -> None:
    """M4 계획서(초안)가 plans/ 에 있어도 단독 승인 M3 은 M1 의 옛 chain 승인 덕에 ready 로 새지 않는다(마감 감사 M29)."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "completed"), ("M4", "pending")))
    write(tmp_path / "plans" / "2026-11-19-m4-draft.md", "# Plan\n")
    payload = _standalone_vs_chained_payload({"approved_by": "user", "plan_sha256": "s3"})
    found, _ = state.chain_next(tmp_path, payload["works"]["m3"], payload)
    assert found is None
    assert state.next_chained_milestone(tmp_path, payload["works"]["m3"], payload) is None


def test_chain_next_chained_work_with_next_plan_is_ready(tmp_path) -> None:
    """같은 상황에서 연쇄로 들어온 M3 은 지금처럼 M4 ready 를 받는다(기존 동작 보존)."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "completed"), ("M4", "pending")))
    write(tmp_path / "plans" / "2026-11-19-m4-draft.md", "# Plan\n")
    payload = _standalone_vs_chained_payload({"approved_by": "chain:m1", "plan_sha256": "s3"})
    found, _ = state.chain_next(tmp_path, payload["works"]["m3"], payload)
    assert found is not None and found["status"] == "ready" and found["milestone_id"] == "M4"


def test_chain_next_chained_work_still_falls_back(tmp_path) -> None:
    """연쇄(approved_by=chain:…)로 들어온 work 는 자기 chain 이 소진돼도 옛 chain 꼬리 M4 를 이어받는다."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M1", "completed"), ("M2", "completed"),
                                            ("M3", "completed"), ("M4", "pending")))
    payload = _standalone_vs_chained_payload({"approved_by": "chain:m1", "plan_sha256": "s3"})
    assert state.chain_scope(payload, payload["works"]["m3"]) == ["m4"]
    found, _ = state.chain_next(tmp_path, payload["works"]["m3"], payload)
    assert found is not None
    assert found["status"] == "needs-plan" and found["milestone_id"] == "M4"


def test_next_chained_normalizes_work_id_chain_items_to_milestone_id(tmp_path) -> None:
    """chain 에 work-id(m158-screens-and-copy)가 저장돼도 milestone ID(M158) 로 읽는다 — 빈 {} 금지."""
    write(tmp_path / "ROADMAP.md", _roadmap(("M156", "completed"), ("M158", "pending")))
    write(tmp_path / "plans" / "2026-11-08-m158-screens.md", "# Plan\n")
    payload = {"schema_version": 1, "works": {
        "m156-frame": {"work_id": "m156-frame", "milestone_id": "M156", "status": "completed",
                       "approval": {"plan_sha256": "s", "chain": ["m158-screens-and-copy"]}},
        "m158-screens-and-copy": {"work_id": "m158-screens-and-copy", "milestone_id": "M158",
                                  "status": "pending"}}}
    assert state.chain_scope(payload, payload["works"]["m156-frame"]) == ["m158"]
    assert "m158" in state.user_approved_milestones(payload)
    found, _ = state.chain_next(tmp_path, payload["works"]["m156-frame"], payload)
    assert found is not None
    assert found["status"] == "ready" and found["milestone_id"] == "M158"
