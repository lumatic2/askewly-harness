#!/usr/bin/env python3
"""Validate and atomically bind an approved plan to harness work state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_STOP_REASONS = [
    "completed",
    "blocked",
    "decision_required",
    "risk_gate",
    "secret_required",
    "external_authority_required",
    "user_stopped",
]
LEAF = re.compile(r"^- \[(?: |x|X)\]\s+(.+)$", re.M)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# MM7 step-1 (2026-07-21): 승인 해시가 파일 전체를 봉인하면 **step 체크박스를 켜는
# 정상 진행**까지 변조로 잡혀 continuation 이 차단된다. 체크박스의 *상태*만 중립화하고
# 나머지는 그대로 봉인한다. append-only 절의 내용도 봉인 대상이 아니다(cs#357).
#
# FA1 step-4 (2026-07-24): ~~"이 정규화는 검증자와 반드시 동일해야 한다"~~ 는 주석
# 계약을 폐지했다 — 정규화 구현은 같은 디렉터리 `harness_work_state.py` 하나이고,
# 작성자(여기)와 검증자가 같은 함수를 import 한다. 사본이 없으면 어긋날 수도 없다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_work_state import normalize_plan_text  # noqa: E402


def plan_fingerprint(path: Path) -> str:
    """승인 시점 해시 — 정규화는 harness_work_state 단일 구현. 읽기 실패는 예외로 터뜨린다
    (검증자 쪽 plan_fingerprint 는 None 을 돌려주지만, 승인 등록은 실패가 정상이다)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return hashlib.sha256(normalize_plan_text(text).encode("utf-8")).hexdigest()


def repo_relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path must be inside repository root: {resolved}") from exc


def step_records(plan_text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for index, match in enumerate(LEAF.finditer(plan_text), start=1):
        label = match.group(1).strip().strip("*")
        raw_id = re.split(r"\s+[—–-]\s+", label, maxsplit=1)[0].strip().strip("*")
        step_id = raw_id if re.fullmatch(r"[A-Za-z0-9._-]+", raw_id) else f"step-{index}"
        # `status` 는 **적지 않는다** (2026-07-23 재조립 P4). 진행의 정본은 계획서
        # 체크박스이고 읽는 쪽(`get_runtime_checklist`)이 매번 거기서 파생한다.
        # 여기 적어 두면 갱신 경로가 approve·report_close 둘뿐이라 중간 진행이
        # 어디에도 안 남고, 디스크 사본이 "completed 인데 next: step-1" 로 굳는다
        # (2026-07-22·23 실측). 명단(id·label)만 남긴다.
        records.append({"id": step_id, "label": label})
    return records


def runtime_session_uuid() -> str | None:
    """승인 세션의 실 UUID 토큰 (2026-07-19 정확 소유 바인딩).

    Claude Code 는 Bash env 로 `CLAUDE_CODE_SESSION_ID` 를 노출한다 — 있으면
    `claude:<uuid>` 로 기록해 continuation hook 이 그 세션만 소유자로 인정한다
    (family fallback 이 같은 레포의 타 세션에 continuation 을 발화해 작업을
    뺏어가던 현상 차단). env 가 없는 런타임(Codex 등)은 None — 기존 판정 유지.
    """
    uuid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    return f"claude:{uuid}" if uuid else None


def default_validator() -> Path:
    candidates = [
        Path(__file__).resolve().with_name("validate_plan_gate.py"),
        Path.home() / ".codex" / "skills" / "harness-run" / "scripts" / "validate_plan_gate.py",
        Path.home() / ".claude" / "skills" / "harness-run" / "scripts" / "validate_plan_gate.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("harness validate_plan_gate.py not found")


def run_validator(plan: Path, validator: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(validator), str(plan), "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stdout.strip() or result.stderr.strip() or "validator failed"
        raise ValueError(detail)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def approve(
    *,
    root: Path,
    plan: Path,
    work_id: str,
    milestone_id: str,
    changeset_path: Path,
    session_id: str,
    validator: Path,
    approved_at: str,
    chain: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    plan = plan.resolve()
    run_validator(plan, validator.resolve())
    steps = step_records(plan.read_text(encoding="utf-8", errors="replace"))
    if len(steps) < 2:
        raise ValueError("approved continuous plan must contain at least two top-level steps")

    state_path = root / ".harness" / "work.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        state = {"schema_version": 1, "active_work_id": None, "works": {}}
    if not isinstance(state, dict) or not isinstance(state.get("works"), dict):
        raise ValueError(".harness/work.json must use the canonical map-based works schema")

    token = session_id if ":" in session_id else f"codex:{session_id}"
    owner_uuid = runtime_session_uuid()
    # MM7 step-2 (2026-07-21): 둘이 다를 때 조용히 하나를 고르면, 나중에 continuation 이
    # "왜 내 세션이 소유자가 아니지"로 침묵한다(HQ1 E2E 에서 혼동으로 관측). 명시한다.
    if owner_uuid and owner_uuid != token:
        print(
            f"note: owner = {owner_uuid} (env CLAUDE_CODE_SESSION_ID 정본). "
            f"--session-id 로 준 {token} 은 session_ids 에만 기록된다.",
            file=sys.stderr,
        )
    work = {
        "work_id": work_id,
        "milestone_id": milestone_id,
        "status": "active",
        "plan_path": repo_relative(root, plan),
        "changeset_path": repo_relative(root, changeset_path),
        "next_step": steps[0]["id"],
        "current_step": steps[0]["id"],
        "steps": steps,
        "execution_mode": "continuous",
        # FA1 step-1 (2026-07-24): `chain` = 승인 게이트에서 **사용자에게 목록으로
        # 제시하고 함께 승인받은** 후속 milestone 들. next-chained 는 이 기록(또는
        # 해당 계획 자체의 영수증)이 있는 후보만 무개입 연쇄 대상으로 인정한다 —
        # 계획서가 plans/ 에 존재한다는 사실만으로는 승인이 아니다(미승인 초안 구멍).
        "approval": {
            "approved_by": "user",
            "approved_at": approved_at,
            "plan_sha256": plan_fingerprint(plan),
            **({"chain": chain} if chain else {}),
        },
        "allowed_stop_reasons": DEFAULT_STOP_REASONS,
        "stop_reason": None,
        "stop_detail": {},
        "session_ids": [token] + ([owner_uuid] if owner_uuid and owner_uuid != token else []),
        "owner_session_uuid": owner_uuid,
        "updated_at": approved_at,
        "notes": "Registered atomically by canonical harness approve_harness_plan.py after plan validation.",
    }
    state["schema_version"] = 1
    state["active_work_id"] = work_id
    state["works"][work_id] = work
    atomic_write_json(state_path, state)
    return work


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--work-id", required=True)
    # 2026-07-23 재조립 P4: horizon 층 폐지로 무의미해졌으나 **인자는 남긴다** —
    # 옛 호출자(문서·스킬 사본·다른 기기 배포본)가 조용히 깨지지 않게 받아서 버린다.
    parser.add_argument("--horizon-id", default=None, help="(폐지 — 무시된다)")
    parser.add_argument("--milestone-id", required=True)
    parser.add_argument("--changeset-path", type=Path, required=True)
    parser.add_argument(
        "--session-id",
        required=True,
        help=(
            "이 승인을 기록할 런타임 세션 토큰(Codex 등 env 를 안 주는 런타임용). "
            "**소유자 판정은 이 값이 아니라 env `CLAUDE_CODE_SESSION_ID` 가 정본**이다 — "
            "env 가 있으면 owner_session_uuid=claude:<env>, 없으면 owner 는 비고 "
            "runtime-family fallback 으로 판정한다. 둘이 다르면 경고를 출력한다."
        ),
    )
    parser.add_argument("--validator", type=Path)
    parser.add_argument("--approved-at", default=date.today().isoformat())
    parser.add_argument(
        "--chain",
        default=None,
        help=(
            "승인 게이트에서 사용자에게 제시하고 함께 승인받은 후속 milestone id 목록"
            "(쉼표 구분). 여기 기록된 것만 next-chained 무개입 연쇄 후보가 된다 — "
            "사용자에게 보여주지 않은 id 를 적으면 안 된다."
        ),
    )
    return parser.parse_args()


def parse_chain(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    items = [item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()]
    return items or None


def main() -> int:
    args = parse_args()
    try:
        work = approve(
            root=args.root,
            plan=args.plan,
            work_id=args.work_id,
            milestone_id=args.milestone_id,
            changeset_path=args.changeset_path,
            session_id=args.session_id,
            validator=args.validator or default_validator(),
            approved_at=args.approved_at,
            chain=parse_chain(args.chain),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"approval gate: FAIL — {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "approved", "work": work}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
