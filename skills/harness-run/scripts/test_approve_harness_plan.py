#!/usr/bin/env python3
"""Regression tests for the canonical approval binding command."""

from __future__ import annotations

import json
from pathlib import Path

from approve_harness_plan import approve, plan_fingerprint, sha256


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(root: Path) -> tuple[Path, Path, Path]:
    plan = root / "docs" / "plans" / "p.md"
    changeset = root / "changesets" / "c" / "README.md"
    validator = root / "validator.py"
    write(plan, "# Plan\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n")
    write(changeset, "# changeset\n")
    write(validator, "raise SystemExit(0)\n")
    return plan, changeset, validator


def test_approval_atomically_registers_hash_and_steps(tmp_path: Path) -> None:
    plan, changeset, validator = fixture(tmp_path)
    work = approve(
        root=tmp_path,
        plan=plan,
        work_id="W1",
        milestone_id="M1",
        changeset_path=changeset,
        session_id="s1",
        validator=validator,
        approved_at="2026-07-13",
    )
    state = json.loads((tmp_path / ".harness" / "work.json").read_text(encoding="utf-8"))
    assert state["active_work_id"] == "W1"
    assert work["approval"]["plan_sha256"] == plan_fingerprint(plan)
    assert work["execution_mode"] == "continuous"
    assert [step["id"] for step in work["steps"]] == ["step-1", "step-2"]
    assert not list((tmp_path / ".harness").glob("*.tmp"))


# FA1 step-1 (2026-07-24): 승인 게이트에서 제시·승인된 연쇄 목록이 영수증에 남아야
# next-chained 가 그 후보만 무개입 연쇄로 인정한다(미승인 초안 구멍 봉쇄).
def test_chain_recorded_in_receipt_only_when_given(tmp_path: Path) -> None:
    plan, changeset, validator = fixture(tmp_path)
    work = approve(
        root=tmp_path,
        plan=plan,
        work_id="W1",
        milestone_id="M1",
        changeset_path=changeset,
        session_id="s1",
        validator=validator,
        approved_at="2026-07-24",
        chain=["M2", "M3"],
    )
    assert work["approval"]["chain"] == ["M2", "M3"]

    work_no_chain = approve(
        root=tmp_path,
        plan=plan,
        work_id="W2",
        milestone_id="M9",
        changeset_path=changeset,
        session_id="s1",
        validator=validator,
        approved_at="2026-07-24",
    )
    assert "chain" not in work_no_chain["approval"]


def test_validator_failure_does_not_create_state(tmp_path: Path) -> None:
    plan, changeset, validator = fixture(tmp_path)
    write(validator, "raise SystemExit(1)\n")
    try:
        approve(
            root=tmp_path,
            plan=plan,
            work_id="W1",
            milestone_id="M1",
            changeset_path=changeset,
            session_id="s1",
            validator=validator,
            approved_at="2026-07-13",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid plan must fail")
    assert not (tmp_path / ".harness" / "work.json").exists()


# MM7 step-1 (2026-07-21): 작성자와 검증자의 정규화가 어긋나면 모든 승인이 즉시 깨진다.
# 여기서 작성자 쪽 계약을 고정한다(검증자 쪽은 the-source-repo test_harness_work_state.py).
def test_plan_fingerprint_ignores_checkbox_state(tmp_path):
    plan = tmp_path / "plan.md"
    body = "- [ ] **step-1 — a**\n- [ ] **step-2 — b**\n"
    plan.write_text(body, encoding="utf-8")
    before = plan_fingerprint(plan)

    plan.write_text(body.replace("- [ ] **step-1", "- [x] **step-1"), encoding="utf-8")
    assert plan_fingerprint(plan) == before


def test_plan_fingerprint_detects_checkbox_label_change(tmp_path):
    plan = tmp_path / "plan.md"
    body = "- [ ] **step-1 — a**\n- [ ] **step-2 — b**\n"
    plan.write_text(body, encoding="utf-8")
    before = plan_fingerprint(plan)

    plan.write_text(body.replace("step-1 — a", "step-1 — 완전히 다른 것"), encoding="utf-8")
    assert plan_fingerprint(plan) != before
