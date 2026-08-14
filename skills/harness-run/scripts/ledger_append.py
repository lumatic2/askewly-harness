#!/usr/bin/env python3
"""Append validated events to a harness execution ledger.

Replaces hand-written JSON at milestone completion (harness-done 완료 hook).
Mirrors check_execution_ledger contract: event ordering, worker/verifier
independence, and non-empty evidence are validated BEFORE appending, so a
typo fails loudly here instead of corrupting the ledger.

Usage:
  ledger_append.py done-claim --task-id X --worker claude \
      --changed-file a.py --test "pytest -q" --evidence "..." \
      --cleanup "no side effects" --risk "none known"
  ledger_append.py verify --task-id X --verifier gate --verdict confirmed \
      --evidence "..." --repro "<command>" \
      --surface-smoke "curl https://... -> 200, 위젯 렌더 확인" [--residual-risk "..."] \
      [--spec-verdict pass --quality-verdict pass] [--near-miss "..."]
      # high-risk 작업(harness-plan non-trivial 위험 기준)은 spec/quality 2축 + near-miss 기록.
      # refuted 후 재검증(re-review)은 새 done_claim 을 먼저 append 해야 한다.
      # --surface-smoke (IMP-013, 2026-07-18): 사용자가 만지는 실표면(배포 사이트·위젯·
      # CLI·배포본)을 실제로 두드린 결과 1줄. 실표면이 없는 작업(문서-only 등)은
      # "none — <이유>" 로 명시한다. 테스트 통과 나열은 실표면 스모크가 아니다 —
      # 7-14 drift: 규정만 있고 실집행이 안 돼 배포 버그를 사용자가 발견했다.
  ledger_append.py complete --task-id X --evidence "..."
  ledger_append.py interruption --source codex_turn_aborted --reason interrupted \
      --session-id 019f4369-... --duration-ms 982 [--task-id X] [--detail "..."]
      # 정지/중단 사유 기록. completion 3종과 독립 이벤트 — done_claim 체인 없이도 append 가능.
      # source: claude_stop | codex_turn_aborted | manual. task_id 는 선택(진행 중 작업이 없을 수 있음).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path(".harness") / "execution-ledger.jsonl"
VERDICTS = {"confirmed", "refuted", "inconclusive"}
AXIS_VERDICTS = {"pass", "fail", "partial"}
INTERRUPTION_SOURCES = {"claude_stop", "codex_turn_aborted", "manual"}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            # 2026-08-06 감사 #9: 구 코드는 조용히 버렸다. 원장은 증거인데 손상을 숨기면
            # "이벤트가 없다"와 "이벤트를 못 읽었다"가 구별되지 않는다 — 앞선 done_claim 이
            # 안 읽히면 검증 독립성 검사가 통째로 헛돈다. 막지는 않되 반드시 말한다.
            print(f"warning: 원장에서 읽을 수 없는 줄을 건너뛴다 ({path}): {line[:80]}",
                  file=sys.stderr)
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def build_done_claim(args: argparse.Namespace) -> dict[str, Any] | str:
    for name, values in (
        ("changed-file", args.changed_files),
        ("test", args.tests),
        ("evidence", args.evidence),
        ("cleanup", args.cleanup),
        ("risk", args.risks),
    ):
        if not values:
            return f"done-claim requires at least one --{name}"
    return {
        "event": "done_claim",
        "task_id": args.task_id,
        "worker": args.worker,
        "changed_files": args.changed_files,
        "tests": args.tests,
        "evidence": args.evidence,
        "cleanup": args.cleanup,
        "risks": args.risks,
    }


def validate_surface_smoke(value: str | None) -> str | None:
    """IMP-013: 실표면 스모크 실집행 증거 — 없으면 명시적 사유가 있어야 한다."""
    text = (value or "").strip()
    if not text:
        return (
            "verify requires --surface-smoke: 실표면(배포 사이트·위젯·CLI·배포본)을 "
            "실제로 두드린 결과 1줄, 실표면이 없으면 'none — <이유>'"
        )
    if text.lower().startswith("none"):
        remainder = text[4:].strip()
        if not remainder.startswith("—") and not remainder.startswith("-"):
            return "surface-smoke 'none' 은 'none — <이유>' 형식이어야 한다"
        if len(remainder.lstrip("—-").strip()) < 3:
            return "surface-smoke 'none' 사유가 비어 있다"
    return None


def build_verify(args: argparse.Namespace, prior: list[dict[str, Any]]) -> dict[str, Any] | str:
    if args.verdict not in VERDICTS:
        return f"verdict must be one of {sorted(VERDICTS)}"
    if not args.evidence:
        return "verify requires at least one --evidence"
    smoke_error = validate_surface_smoke(args.surface_smoke)
    if smoke_error:
        return smoke_error
    claims = [r for r in prior if r.get("event") == "done_claim" and r.get("task_id") == args.task_id]
    if not claims:
        return f"no prior done_claim for task_id '{args.task_id}'"
    if any(str(c.get("worker")) == args.verifier for c in claims):
        return "verifier must be independent from done_claim.worker"
    axes = (args.spec_verdict, args.quality_verdict)
    if (axes[0] is None) != (axes[1] is None):
        return "spec-verdict and quality-verdict must be provided together"
    if axes[0] is not None:
        for name, value in (("spec-verdict", axes[0]), ("quality-verdict", axes[1])):
            if value not in AXIS_VERDICTS:
                return f"{name} must be one of {sorted(AXIS_VERDICTS)}"
        if args.verdict == "confirmed" and (axes[0] != "pass" or axes[1] != "pass"):
            return "confirmed requires spec-verdict=pass and quality-verdict=pass"
    # re-review: refuted 이후의 재검증은 수정을 반영한 새 done_claim 을 경유해야 한다
    last_refuted_index = max(
        (
            i
            for i, r in enumerate(prior)
            if r.get("event") == "adversarial_verify"
            and r.get("task_id") == args.task_id
            and r.get("verdict") == "refuted"
        ),
        default=None,
    )
    if last_refuted_index is not None and not any(
        r.get("event") == "done_claim" and r.get("task_id") == args.task_id
        for r in prior[last_refuted_index + 1 :]
    ):
        return "re-review after a refuted verify requires a new done_claim first"
    record = {
        "event": "adversarial_verify",
        "task_id": args.task_id,
        "verifier": args.verifier,
        "verdict": args.verdict,
        "evidence": args.evidence,
        "repro": args.repro,
        "surface_smoke": args.surface_smoke.strip(),
    }
    if axes[0] is not None:
        record["spec_verdict"] = axes[0]
        record["quality_verdict"] = axes[1]
    if args.near_misses:
        record["near_misses"] = args.near_misses
    if args.residual_risk:
        record["residual_risk"] = args.residual_risk
    return record


def build_complete(args: argparse.Namespace, prior: list[dict[str, Any]]) -> dict[str, Any] | str:
    if not args.evidence:
        return "complete requires at least one --evidence"
    if not any(r.get("event") == "done_claim" and r.get("task_id") == args.task_id for r in prior):
        return f"no prior done_claim for task_id '{args.task_id}'"
    if not any(
        r.get("event") == "adversarial_verify"
        and r.get("task_id") == args.task_id
        and r.get("verdict") == "confirmed"
        for r in prior
    ):
        return "task_completed requires prior confirmed adversarial_verify"
    return {"event": "task_completed", "task_id": args.task_id, "evidence": args.evidence}


def build_interruption(args: argparse.Namespace) -> dict[str, Any] | str:
    source = (args.source or "").strip()
    reason = (args.reason or "").strip()
    if not source:
        return "interruption requires --source"
    if source not in INTERRUPTION_SOURCES:
        return f"source must be one of {sorted(INTERRUPTION_SOURCES)}"
    if not reason:
        return "interruption requires --reason"
    record: dict[str, Any] = {
        "event": "interruption",
        "ts": args.ts or datetime.now(timezone.utc).isoformat(),
        "source": source,
        "reason": reason,
    }
    if args.session_id:
        record["session_id"] = args.session_id
    if args.duration_ms is not None:
        record["duration_ms"] = args.duration_ms
    if args.task_id:
        record["task_id"] = args.task_id
    if args.detail:
        record["detail"] = args.detail
    return record


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER), help="ledger path (default .harness/execution-ledger.jsonl)")
    sub = parser.add_subparsers(dest="command", required=True)

    claim = sub.add_parser("done-claim")
    claim.add_argument("--task-id", required=True)
    claim.add_argument("--worker", required=True)
    claim.add_argument("--changed-file", action="append", dest="changed_files", default=[])
    claim.add_argument("--test", action="append", dest="tests", default=[])
    claim.add_argument("--evidence", action="append", default=[])
    claim.add_argument("--cleanup", action="append", default=[])
    claim.add_argument("--risk", action="append", dest="risks", default=[])

    verify = sub.add_parser("verify")
    verify.add_argument("--task-id", required=True)
    verify.add_argument("--verifier", required=True)
    verify.add_argument("--verdict", required=True)
    verify.add_argument("--evidence", action="append", default=[])
    verify.add_argument("--repro", required=True)
    verify.add_argument("--surface-smoke", dest="surface_smoke", help="실표면 실행 결과 1줄 또는 'none — <이유>' (IMP-013)")
    verify.add_argument("--residual-risk")
    verify.add_argument("--spec-verdict", dest="spec_verdict")
    verify.add_argument("--quality-verdict", dest="quality_verdict")
    verify.add_argument("--near-miss", action="append", dest="near_misses", default=[])

    complete = sub.add_parser("complete")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--evidence", action="append", default=[])
    complete.add_argument("--summary", help="사용자용 한 문장 — 무엇이 어떻게 됐나 (알림에 그대로 나감. 파일 경로 나열 금지)")

    # CS8 step-3 (2026-07-17): 완료 의식 다이어트 — 3커맨드(done-claim→verify→complete)를
    # 1호출로. 필수 필드·순서·독립성 검증은 각 builder 를 그대로 통과하므로 강도 불변.
    close = sub.add_parser("close")
    close.add_argument("--task-id", required=True)
    close.add_argument("--worker", required=True)
    close.add_argument("--changed-file", action="append", dest="changed_files", default=[])
    close.add_argument("--test", action="append", dest="tests", default=[])
    close.add_argument("--evidence", action="append", default=[])
    close.add_argument("--cleanup", action="append", default=[])
    close.add_argument("--risk", action="append", dest="risks", default=[])
    close.add_argument("--verifier", required=True)
    close.add_argument("--verdict", required=True)
    close.add_argument("--repro", required=True)
    close.add_argument("--surface-smoke", dest="surface_smoke", help="실표면 실행 결과 1줄 또는 'none — <이유>' (IMP-013)")
    close.add_argument("--residual-risk")
    close.add_argument("--spec-verdict", dest="spec_verdict")
    close.add_argument("--quality-verdict", dest="quality_verdict")
    close.add_argument("--near-miss", action="append", dest="near_misses", default=[])
    close.add_argument("--summary", help="사용자용 한 문장 — 무엇이 어떻게 됐나 (알림에 그대로 나감. 파일 경로 나열 금지)")

    interruption = sub.add_parser("interruption")
    interruption.add_argument("--source", required=True)
    interruption.add_argument("--reason", required=True)
    interruption.add_argument("--session-id", dest="session_id")
    interruption.add_argument("--duration-ms", dest="duration_ms", type=int)
    interruption.add_argument("--task-id", dest="task_id")
    interruption.add_argument("--detail")
    interruption.add_argument("--ts", help="ISO timestamp override (default: now, UTC)")

    return parser.parse_args(argv)


def _find_work_for_task(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    works = state.get("works")
    items = list(works.values()) if isinstance(works, dict) else works if isinstance(works, list) else []
    for w in items:
        if isinstance(w, dict) and task_id in {str(w.get("milestone_id") or ""), str(w.get("work_id") or "")}:
            return w
    return None


def stage_completion_summary(ledger: Path, task_id: str, summary: str | None = None) -> None:
    """milestone 완료 이벤트는 무알림 (2026-07-19 사용자 확정 — 조기 "작업 완료" 오발사 수리).

    구 notify_completion 은 task_completed append 마다 "✅ 작업 완료"를 발사했는데,
    여러 milestone 을 연쇄로 도는 세션에서는 중간 완료가 전체 완료처럼 읽혔다
    (2026-07-19 00:49 discord-agents·ui-dictionary 실측). 여기서는 사용자용 요약만
    work.json `completion_summary` 에 적재하고, 최종 "✅ 작업 완료" 알림은 Stop 훅
    (harness_continuation_hook.maybe_notify_final_completion)이 "active_work_id 가
    completed 를 가리키고 다른 active work 가 없다"는 조건에서 1회 발사한다.
    fail-silent: 적재 실패가 ledger append 결과를 바꾸지 않는다.
    """
    try:
        root = ledger.resolve().parent.parent  # <repo>/.harness/execution-ledger.jsonl
        work_path = root / ".harness" / "work.json"
        if not work_path.is_file():
            return
        state = json.loads(work_path.read_text(encoding="utf-8"))
        work = _find_work_for_task(state, task_id)
        if work is None:
            return
        if summary and summary.strip():
            work["completion_summary"] = summary.strip()
            work_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ledger = Path(args.ledger)
    prior = load_records(ledger)

    if args.command == "close":
        # 3-event 순차 append — 각 builder 의 검증(순서·독립성·필수 필드)을 그대로 통과.
        records = []
        rec = build_done_claim(args)
        if isinstance(rec, str):
            return fail(rec)
        records.append(rec)
        rec = build_verify(args, prior + records)
        if isinstance(rec, str):
            return fail(rec)
        records.append(rec)
        rec = build_complete(args, prior + records)
        if isinstance(rec, str):
            return fail(rec)
        records.append(rec)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8", newline="\n") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"appended done_claim+adversarial_verify+task_completed for {args.task_id} -> {ledger}")
        stage_completion_summary(ledger, str(args.task_id), getattr(args, "summary", None))
        return 0

    if args.command == "done-claim":
        record = build_done_claim(args)
    elif args.command == "verify":
        record = build_verify(args, prior)
    elif args.command == "complete":
        record = build_complete(args, prior)
    else:
        record = build_interruption(args)

    if isinstance(record, str):
        return fail(record)

    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    target = record.get("task_id") or "(no task)"
    print(f"appended {record['event']} for {target} -> {ledger}")
    if record["event"] == "task_completed":
        stage_completion_summary(ledger, str(record.get("task_id") or ""), getattr(args, "summary", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
