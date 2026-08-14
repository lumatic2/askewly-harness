#!/usr/bin/env python3
"""Contract tests for ledger_append.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import ledger_append


def run_chain(tmp: Path) -> Path:
    ledger = tmp / ".harness" / "execution-ledger.jsonl"
    args = ["--ledger", str(ledger)]
    assert ledger_append.main(args + [
        "done-claim", "--task-id", "T1", "--worker", "claude",
        "--changed-file", "a.py", "--test", "pytest -q", "--evidence", "e1",
        "--cleanup", "none", "--risk", "none",
    ]) == 0
    assert ledger_append.main(args + [
        "verify", "--task-id", "T1", "--verifier", "gate", "--verdict", "confirmed",
        "--evidence", "re-ran", "--repro", "pytest -q", "--surface-smoke", "cli 실행 -> 정상 출력",
    ]) == 0
    assert ledger_append.main(args + [
        "complete", "--task-id", "T1", "--evidence", "verified",
    ]) == 0
    return ledger


def test_happy_chain_appends_three_valid_events():
    with tempfile.TemporaryDirectory() as td:
        ledger = run_chain(Path(td))
        lines = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
        assert [r["event"] for r in lines] == ["done_claim", "adversarial_verify", "task_completed"]


def test_verify_without_done_claim_fails():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        code = ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T9", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ])
        assert code == 1
        assert not Path(ledger).exists()


def test_verifier_must_differ_from_worker():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        assert ledger_append.main([
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a", "--test", "t", "--evidence", "e",
            "--cleanup", "c", "--risk", "r",
        ]) == 0
        code = ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "claude",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ])
        assert code == 1


def test_complete_requires_confirmed_verify():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        assert ledger_append.main([
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a", "--test", "t", "--evidence", "e",
            "--cleanup", "c", "--risk", "r",
        ]) == 0
        assert ledger_append.main([
            "--ledger", ledger, "complete", "--task-id", "T1", "--evidence", "x",
        ]) == 1
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "refuted", "--evidence", "broken", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ]) == 0
        assert ledger_append.main([
            "--ledger", ledger, "complete", "--task-id", "T1", "--evidence", "x",
        ]) == 1


def test_axis_verdicts_are_paired_and_consistent():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        assert ledger_append.main([
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a", "--test", "t", "--evidence", "e",
            "--cleanup", "c", "--risk", "r",
        ]) == 0
        # 한 축만 주면 거부
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
            "--spec-verdict", "pass",
        ]) == 1
        # 축 fail 인데 aggregate confirmed 면 거부
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
            "--spec-verdict", "pass", "--quality-verdict", "fail",
        ]) == 1
        # 2축 pass + near-miss 는 confirmed 와 함께 기록됨
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
            "--spec-verdict", "pass", "--quality-verdict", "pass",
            "--near-miss", "edge case almost missed: empty input",
        ]) == 0
        last = json.loads(Path(ledger).read_text(encoding="utf-8").splitlines()[-1])
        assert last["spec_verdict"] == "pass"
        assert last["quality_verdict"] == "pass"
        assert last["near_misses"] == ["edge case almost missed: empty input"]


def test_re_review_after_refuted_requires_new_done_claim():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        claim = [
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a", "--test", "t", "--evidence", "e",
            "--cleanup", "c", "--risk", "r",
        ]
        assert ledger_append.main(claim) == 0
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "refuted", "--evidence", "broken", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ]) == 0
        # refuted 직후 새 done_claim 없이 재검증 시도 → 거부
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "fixed", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ]) == 1
        # 수정 반영 done_claim 후에는 재검증 허용
        assert ledger_append.main(claim) == 0
        assert ledger_append.main([
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "fixed", "--repro", "y", "--surface-smoke", "none — 픽스처(실표면 없음)",
        ]) == 0


def test_done_claim_requires_all_list_fields():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        code = ledger_append.main([
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a",
        ])
        assert code == 1


def test_interruption_appends_without_task_id():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        assert ledger_append.main([
            "--ledger", ledger, "interruption", "--source", "codex_turn_aborted",
            "--reason", "interrupted", "--session-id", "019f4369-...",
            "--duration-ms", "982", "--ts", "2026-07-08T21:05:39Z",
        ]) == 0
        record = json.loads(Path(ledger).read_text(encoding="utf-8").splitlines()[-1])
        assert record["event"] == "interruption"
        assert record["source"] == "codex_turn_aborted"
        assert record["reason"] == "interrupted"
        assert record["duration_ms"] == 982
        assert "task_id" not in record


def test_interruption_missing_reason_fails():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        code = ledger_append.main([
            "--ledger", ledger, "interruption", "--source", "manual", "--reason", "",
        ])
        assert code == 1
        assert not Path(ledger).exists()


def test_interruption_invalid_source_fails():
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        code = ledger_append.main([
            "--ledger", ledger, "interruption", "--source", "bogus", "--reason", "x",
        ])
        assert code == 1
        assert not Path(ledger).exists()


if __name__ == "__main__":
    test_happy_chain_appends_three_valid_events()
    test_verify_without_done_claim_fails()
    test_verifier_must_differ_from_worker()
    test_complete_requires_confirmed_verify()
    test_axis_verdicts_are_paired_and_consistent()
    test_re_review_after_refuted_requires_new_done_claim()
    test_done_claim_requires_all_list_fields()
    test_interruption_appends_without_task_id()
    test_interruption_missing_reason_fails()
    test_interruption_invalid_source_fails()
    print("test_ledger_append.py: PASS")


def test_verify_requires_surface_smoke():
    # IMP-013: 실표면 스모크 없는 verify 는 거부 — 'none' 은 이유가 있어야 허용
    with tempfile.TemporaryDirectory() as td:
        ledger = str(Path(td) / "ledger.jsonl")
        claim = [
            "--ledger", ledger, "done-claim", "--task-id", "T1", "--worker", "claude",
            "--changed-file", "a", "--test", "t", "--evidence", "e",
            "--cleanup", "c", "--risk", "r",
        ]
        assert ledger_append.main(claim) == 0
        base = [
            "--ledger", ledger, "verify", "--task-id", "T1", "--verifier", "gate",
            "--verdict", "confirmed", "--evidence", "x", "--repro", "y",
        ]
        assert ledger_append.main(base) == 1                                      # 부재 = 거부
        assert ledger_append.main(base + ["--surface-smoke", "none"]) == 1        # 이유 없는 none = 거부
        assert ledger_append.main(base + ["--surface-smoke", "none — 문서-only 작업"]) == 0
        last = json.loads(Path(ledger).read_text(encoding="utf-8").splitlines()[-1])
        assert last["surface_smoke"].startswith("none")
