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
