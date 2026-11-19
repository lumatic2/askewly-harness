#!/usr/bin/env python3
"""Regression tests for the canonical approval binding command."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from approve_harness_plan import approve, plan_fingerprint, sha256


@pytest.fixture(autouse=True)
def _hermetic_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """h-e M32: approve 가 cwd≠root 면 세션 초점을 실 홈에 쓴다 — 테스트는 tmp 홈으로 밀폐(실측 유출 1건)."""
    home = tmp_path / "_home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HARNESS_USER_HOME", str(home))


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


# ── M9 step-2 (2026-09-02): 같은 회차의 두 번째 승인이 첫 승인을 지우지 않는다 ──
def _second_plan(root: Path) -> Path:
    plan = root / "docs" / "plans" / "p2.md"
    write(plan, "# Plan 2\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n")
    return plan


def test_second_approval_keeps_the_pointer_and_reports_the_other(tmp_path: Path, capsys) -> None:
    plan, changeset, validator = fixture(tmp_path)
    plan2 = _second_plan(tmp_path)
    common = dict(
        root=tmp_path, changeset_path=changeset, validator=validator, approved_at="2026-09-02"
    )
    approve(plan=plan, work_id="W1", milestone_id="M1", session_id="s1", **common)
    before = json.loads((tmp_path / ".harness" / "work.json").read_text(encoding="utf-8"))["works"]["W1"]
    capsys.readouterr()

    approve(plan=plan2, work_id="W2", milestone_id="M2", session_id="s2", **common)
    out = capsys.readouterr().out
    state = json.loads((tmp_path / ".harness" / "work.json").read_text(encoding="utf-8"))

    assert set(state["works"]) == {"W1", "W2"}
    assert state["active_work_id"] == "W1"
    # 새로 등록한 work 의 발사 프롬프트가 쓸 "같은 회차에 승인된 다른 계획" 목록.
    assert "active_work_id 유지(W1)" in out and "다른 승인: [W1]" in out
    # 등록이 다른 work 를 건드리지 않았다 (failure probe).
    assert state["works"]["W1"] == before
    assert before["approval"]["plan_sha256"] == plan_fingerprint(plan)


def test_approval_moves_the_pointer_when_the_previous_work_is_terminal(tmp_path: Path) -> None:
    plan, changeset, validator = fixture(tmp_path)
    plan2 = _second_plan(tmp_path)
    common = dict(
        root=tmp_path, changeset_path=changeset, validator=validator, approved_at="2026-09-02"
    )
    approve(plan=plan, work_id="W1", milestone_id="M1", session_id="s1", **common)
    state_path = tmp_path / ".harness" / "work.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["works"]["W1"]["status"] = "completed"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    approve(plan=plan2, work_id="W2", milestone_id="M2", session_id="s2", **common)
    assert json.loads(state_path.read_text(encoding="utf-8"))["active_work_id"] == "W2"


def test_other_live_approvals_are_reported_even_when_the_pointer_moves(tmp_path: Path, capsys) -> None:
    """포인터가 종결이어도 살아 있는 승인은 고지된다 (리뷰 지적 4).

    발사 프롬프트는 이 줄의 부재를 "다른 승인 없음"으로 읽는다 — 침묵하면
    M9 가 없애려던 오식별이 그대로 재발한다.
    """
    plan, changeset, validator = fixture(tmp_path)
    plan2 = _second_plan(tmp_path)
    plan3 = tmp_path / "docs" / "plans" / "p3.md"
    write(plan3, "# Plan 3\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n")
    common = dict(
        root=tmp_path, changeset_path=changeset, validator=validator, approved_at="2026-09-02"
    )
    approve(plan=plan, work_id="W0", milestone_id="M0", session_id="s0", **common)
    approve(plan=plan2, work_id="W1", milestone_id="M1", session_id="s1", **common)
    state_path = tmp_path / ".harness" / "work.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["works"]["W0"]["status"] = "completed"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()

    approve(plan=plan3, work_id="W2", milestone_id="M2", session_id="s2", **common)
    out = capsys.readouterr().out
    assert json.loads(state_path.read_text(encoding="utf-8"))["active_work_id"] == "W2"
    assert "다른 승인: [W1]" in out


def test_cross_repo_approval_sets_session_focus(tmp_path: Path, monkeypatch, capsys) -> None:
    """h-e M32 D10: --root 가 cwd 레포와 다르면 초점 파일이 생기고, 같으면 생기지 않는다."""
    import harness_focus as hf
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-x")
    target = tmp_path / "target"
    plan, changeset, validator = fixture(target)
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    approve(root=target, plan=plan, work_id="W1", milestone_id="M1", changeset_path=changeset,
            session_id="s1", validator=validator, approved_at="2026-09-05")
    assert "focus: " in capsys.readouterr().out
    assert hf.resolve_root("sess-x", elsewhere) == target.resolve()
    # 같은 레포에서 승인하면 초점을 만들지 않는다
    hf.main(["clear", "--session", "sess-x"])
    monkeypatch.chdir(target)
    approve(root=target, plan=plan, work_id="W2", milestone_id="M2", changeset_path=changeset,
            session_id="s1", validator=validator, approved_at="2026-09-05")
    assert not hf.focus_path("sess-x").is_file()


# ── --validator 는 게이트 스크립트 경로다 (fresh 검증자 라벨이 아니다) ───────
# 2026-09-22 스테이징 스모크 관측: `--validator plan-verifier` 가 경로로 해석돼
# 승인이 죽었다. 에러가 원인을 직접 말하게 한 계약을 고정한다.
from approve_harness_plan import default_validator, resolve_validator


def test_validator_label_raises_actionable_error():
    with pytest.raises(ValueError) as e:
        resolve_validator(Path("plan-verifier"))
    msg = str(e.value)
    assert "게이트 스크립트 경로" in msg
    assert "plan-verifier" in msg


def test_validator_omitted_falls_back_to_default_gate():
    assert resolve_validator(None) == default_validator()


def test_existing_path_is_passed_through(tmp_path: Path):
    gate = tmp_path / "custom_gate.py"
    gate.write_text("", encoding="utf-8")
    assert resolve_validator(gate) == gate


# M23 step-1 (2026-10-26): 목표 승인(chain) 이 다음 milestone 계획의 실행 승인을 겸한다.
# 단 그 계획이 검증자를 거쳤고 사용자 몫 미결 결정이 없을 때만 — 아니면 경계에서 멈춘다.
CHAINED_PLAN = (
    "# Plan\n"
    "## 결정 로그\n- D1: x\n- status: resolved\n"
    "## 검증자 지적 처분\n| 지적 | 층 | 처분 | 이유 |\n|---|---|---|---|\n| a | L1 | 반영 | b |\n"
    "- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n"
)


def _goal_receipt(root: Path, validator: Path, changeset: Path) -> None:
    first = root / "plans" / "m1.md"
    write(first, "# Plan\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n")
    approve(
        root=root, plan=first, work_id="W1", milestone_id="M1",
        changeset_path=changeset, session_id="s1", validator=validator,
        approved_at="2026-10-26", chain=["M2", "M3"],
    )


def test_chained_from_inherits_chain_and_marks_approver(tmp_path: Path) -> None:
    _, changeset, validator = fixture(tmp_path)
    _goal_receipt(tmp_path, validator, changeset)
    plan = tmp_path / "plans" / "m2.md"
    write(plan, CHAINED_PLAN)
    work = approve(
        root=tmp_path, plan=plan, work_id="W2", milestone_id="M2",
        changeset_path=changeset, session_id="s1", validator=validator,
        approved_at="2026-10-27", chained_from="W1",
    )
    assert work["approval"]["approved_by"] == "chain:W1"
    assert work["approval"]["chain"] == ["M2", "M3"]


@pytest.mark.parametrize(
    "mutate, milestone",
    [
        (lambda t: t.replace("- D1: x\n", "- D1: x — 사용자 몫 미결\n"), "M2"),
        (lambda t: t, "M9"),
    ],
    ids=["open-user-decision", "outside-chain"],
)
def test_chained_from_refuses_open_user_decision_or_outside_chain(tmp_path: Path, mutate, milestone) -> None:
    _, changeset, validator = fixture(tmp_path)
    _goal_receipt(tmp_path, validator, changeset)
    plan = tmp_path / "plans" / "m2.md"
    write(plan, mutate(CHAINED_PLAN))
    before = (tmp_path / ".harness" / "work.json").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        approve(
            root=tmp_path, plan=plan, work_id="W2", milestone_id=milestone,
            changeset_path=changeset, session_id="s1", validator=validator,
            approved_at="2026-10-27", chained_from="W1",
        )
    assert (tmp_path / ".harness" / "work.json").read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("| a | L1 | 반영 | b |\n", "none — 연쇄 계획(검증자 없음)\n"),
        lambda t: t.replace("| 지적 | 층 | 처분 | 이유 |\n", "").replace("|---|---|---|---|\n", "").replace("| a | L1 | 반영 | b |\n", ""),
    ],
    ids=["none-line", "empty-section"],
)
def test_chained_plan_without_verifier_is_approved(tmp_path: Path, mutate) -> None:
    """2026-11-16 사용자 결정 — 연쇄 계획에서 plan-verifier 를 뺐다. 처분이 none 이어도 승인된다."""
    _, changeset, validator = fixture(tmp_path)
    _goal_receipt(tmp_path, validator, changeset)
    plan = tmp_path / "plans" / "m2.md"
    write(plan, mutate(CHAINED_PLAN))
    work = approve(
        root=tmp_path, plan=plan, work_id="W2", milestone_id="M2",
        changeset_path=changeset, session_id="s1", validator=validator,
        approved_at="2026-10-27", chained_from="W1",
    )
    assert work["approval"]["approved_by"] == "chain:W1"


# M26 step-2 (2026-11-18): 펼치는 계획 — 메인 영수증의 갈래 목록이 갈래 자기 승인의 유일한 근거다.
def _fanout_setup(tmp_path: Path, branch_id: str = "alpha") -> tuple[Path, Path, Path, Path]:
    main = tmp_path / "main"
    _, changeset, validator = fixture(main)
    main_plan = main / "plans" / "main.md"
    write(main_plan, "# Plan\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n")
    approve(
        root=main, plan=main_plan, work_id="M5-fan", milestone_id="M5",
        changeset_path=changeset, session_id="s1", validator=validator,
        approved_at="2026-11-18", fanout=["alpha", "beta"],
    )
    branch = tmp_path / "wt-alpha"
    write(main / ".harness" / "fanout" / "M5-fan.json", json.dumps({
        "main_work_id": "M5-fan", "base_branch": "master",
        "branches": [
            {"id": "alpha", "branch": "m5-alpha", "worktree_path": str(branch), "state": "running"},
            {"id": "beta", "branch": "m5-beta", "worktree_path": str(tmp_path / "wt-beta"), "state": "running"},
        ],
    }, ensure_ascii=False))
    write(branch / ".harness" / "fanout" / "branch.json", json.dumps({
        "main_work_id": "M5-fan", "main_root": str(main), "milestone_id": "M5",
        "branch_id": branch_id, "title": "t", "dod": "d", "owns": ["src/a.py"],
        "base_branch": "master",
    }, ensure_ascii=False))
    bplan = branch / "plans" / "branch.md"
    write(bplan, CHAINED_PLAN)
    bchange = branch / "changesets" / "c" / "README.md"
    write(bchange, "# c\n")
    return main, branch, bplan, bchange


def test_fanout_recorded_in_main_receipt(tmp_path: Path) -> None:
    main, _, _, _ = _fanout_setup(tmp_path)
    state = json.loads((main / ".harness" / "work.json").read_text(encoding="utf-8"))
    assert state["works"]["M5-fan"]["approval"]["fanout"] == ["alpha", "beta"]


def test_fanned_from_approves_listed_branch(tmp_path: Path) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    work = approve(
        root=branch, plan=bplan, work_id="M5-alpha", milestone_id="M5",
        changeset_path=bchange, session_id="s1", validator=main / "validator.py",
        approved_at="2026-11-18", fanned_from="M5-fan",
    )
    assert work["approval"]["approved_by"].startswith("fanout:")
    assert work["approval"]["approved_by"] == "fanout:M5-fan"
    assert (branch / ".harness" / "work.json").exists()


def test_fanned_from_rejects_unlisted_branch(tmp_path: Path) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path, branch_id="gamma")
    with pytest.raises(ValueError, match="gamma"):
        approve(
            root=branch, plan=bplan, work_id="M5-gamma", milestone_id="M5",
            changeset_path=bchange, session_id="s1", validator=main / "validator.py",
            approved_at="2026-11-18", fanned_from="M5-fan",
        )
    assert not (branch / ".harness" / "work.json").exists()


def test_fanned_from_rejects_pending_user_decision(tmp_path: Path) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    write(bplan, CHAINED_PLAN.replace("- D1: x\n", "- D1: x — 사용자 몫 미결\n"))
    with pytest.raises(ValueError, match="사용자 몫 미결"):
        approve(
            root=branch, plan=bplan, work_id="M5-alpha", milestone_id="M5",
            changeset_path=bchange, session_id="s1", validator=main / "validator.py",
            approved_at="2026-11-18", fanned_from="M5-fan",
        )
    assert not (branch / ".harness" / "work.json").exists()


@pytest.mark.parametrize(
    "bad, expected",
    [
        ("no-packet", "전달물"),
        ("wrong-main", "main_work_id"),
        ("wrong-milestone", "milestone_id"),
    ],
)
def test_fanned_from_rejects_packet_mismatch(tmp_path: Path, bad: str, expected: str) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    packet = branch / ".harness" / "fanout" / "branch.json"
    fanned_from, milestone = "M5-fan", "M5"
    if bad == "no-packet":
        packet.unlink()
    elif bad == "wrong-main":
        fanned_from = "M5-other"
    else:
        milestone = "M6"
    with pytest.raises(ValueError, match=expected):
        approve(
            root=branch, plan=bplan, work_id="M5-alpha", milestone_id=milestone,
            changeset_path=bchange, session_id="s1", validator=main / "validator.py",
            approved_at="2026-11-18", fanned_from=fanned_from,
        )


def _edit_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _approve_branch(main: Path, branch: Path, bplan: Path, bchange: Path) -> dict:
    return approve(
        root=branch, plan=bplan, work_id="M5-alpha", milestone_id="M5",
        changeset_path=bchange, session_id="s1", validator=main / "validator.py",
        approved_at="2026-11-18", fanned_from="M5-fan",
    )


def _branch_entry(registry: dict, branch_id: str = "alpha") -> dict:
    return next(b for b in registry["branches"] if b["id"] == branch_id)


@pytest.mark.parametrize(
    "case, expected",
    [
        ("no-main-work-json", "메인 영수증을 읽지 못했다"),
        ("main-without-fanout", "갈래 목록"),
        ("empty-branch-id", "branch_id"),
        ("main-completed", "active"),
        ("main-missing-work", "갈래 목록"),
        ("registry-missing", "등록부"),
        ("registry-no-entry", "등록부"),
        ("registry-dropped", "running"),
        ("registry-ready", "running"),
        ("registry-other-path", "worktree_path"),
    ],
)
def test_fanned_from_requires_live_authority(tmp_path: Path, case: str, expected: str) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    main_state = main / ".harness" / "work.json"
    registry = main / ".harness" / "fanout" / "M5-fan.json"
    packet = branch / ".harness" / "fanout" / "branch.json"
    if case == "no-main-work-json":
        main_state.unlink()
    elif case == "main-without-fanout":
        _edit_json(main_state, lambda d: d["works"]["M5-fan"]["approval"].pop("fanout"))
    elif case == "empty-branch-id":
        _edit_json(packet, lambda d: d.update(branch_id=""))
    elif case == "main-completed":
        _edit_json(main_state, lambda d: d["works"]["M5-fan"].update(status="completed"))
    elif case == "main-missing-work":
        _edit_json(main_state, lambda d: d["works"].pop("M5-fan"))
    elif case == "registry-missing":
        registry.unlink()
    elif case == "registry-no-entry":
        _edit_json(registry, lambda d: d["branches"].remove(_branch_entry(d)))
    elif case == "registry-dropped":
        _edit_json(registry, lambda d: _branch_entry(d).update(state="dropped"))
    elif case == "registry-ready":
        _edit_json(registry, lambda d: _branch_entry(d).update(state="ready"))
    else:
        _edit_json(registry, lambda d: _branch_entry(d).update(worktree_path=str(tmp_path / "wt-elsewhere")))
    with pytest.raises(ValueError, match=expected):
        _approve_branch(main, branch, bplan, bchange)
    assert not (branch / ".harness" / "work.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="경로 대소문자·구분자 흡수는 Windows 몫")
def test_fanned_from_normalizes_registry_path(tmp_path: Path) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    registry = main / ".harness" / "fanout" / "M5-fan.json"
    variant = str(branch).upper().replace("\\", "/")
    assert variant != str(branch)
    _edit_json(registry, lambda d: _branch_entry(d).update(worktree_path=variant))
    work = _approve_branch(main, branch, bplan, bchange)
    assert work["approval"]["approved_by"] == "fanout:M5-fan"


FANOUT_LIST_PLAN = (
    "# Plan\n"
    "## 갈래 목록\n"
    "- 펼침 판정: 펼침 — 셋 다 참\n"
    "- alpha · 가 · 완료 기준: x · 소유: a/**\n"
    "- beta · 나 · 완료 기준: y · 소유: b/**\n"
    "## 단계\n"
    "- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n"
)
NO_LIST_PLAN = "# Plan\n- [ ] **step-1 — one**\n- [ ] **step-2 — two**\n"


def _approve_main(tmp_path: Path, plan_text: str, fanout: list[str]) -> dict:
    main = tmp_path / "main2"
    _, changeset, validator = fixture(main)
    plan = main / "plans" / "main.md"
    write(plan, plan_text)
    return approve(
        root=main, plan=plan, work_id="M5-fan", milestone_id="M5",
        changeset_path=changeset, session_id="s1", validator=validator,
        approved_at="2026-11-18", fanout=fanout,
    )


def test_fanout_matching_plan_list_is_recorded(tmp_path: Path) -> None:
    work = _approve_main(tmp_path, FANOUT_LIST_PLAN, ["beta", "alpha"])
    assert work["approval"]["fanout"] == ["beta", "alpha"]


def test_fanout_without_list_section_checks_only_id_format(tmp_path: Path) -> None:
    work = _approve_main(tmp_path, NO_LIST_PLAN, ["x", "y"])
    assert work["approval"]["fanout"] == ["x", "y"]


@pytest.mark.parametrize(
    "fanout, expected",
    [
        (["alpha"], "빠진.*beta"),
        (["alpha", "beta", "gamma"], "남는.*gamma"),
        (["alpha", "gamma"], "빠진.*beta"),
    ],
)
def test_fanout_must_equal_plan_branch_list(tmp_path: Path, fanout: list[str], expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        _approve_main(tmp_path, FANOUT_LIST_PLAN, fanout)
    assert not (tmp_path / "main2" / ".harness" / "work.json").exists()


@pytest.mark.parametrize("bad_id", ["Alpha", "al pha", "a_b", "알파"])
def test_fanout_rejects_malformed_branch_id(tmp_path: Path, bad_id: str) -> None:
    with pytest.raises(ValueError, match=r"\[a-z0-9-\]\+"):
        _approve_main(tmp_path, NO_LIST_PLAN, ["alpha", bad_id])
    assert not (tmp_path / "main2" / ".harness" / "work.json").exists()


def test_fanout_and_fanned_from_are_exclusive(tmp_path: Path) -> None:
    main, branch, bplan, bchange = _fanout_setup(tmp_path)
    with pytest.raises(ValueError):
        approve(
            root=branch, plan=bplan, work_id="M5-alpha", milestone_id="M5",
            changeset_path=bchange, session_id="s1", validator=main / "validator.py",
            approved_at="2026-11-18", fanned_from="M5-fan", fanout=["x", "y"],
        )
