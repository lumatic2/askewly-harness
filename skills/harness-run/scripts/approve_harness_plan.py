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
from harness_work_state import continuable_works, normalize_plan_text  # noqa: E402
import harness_focus  # noqa: E402  (h-e M32 D10 — 교차 레포 승인 시 세션 초점 자동 set)


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


def resolve_validator(value: Path | None) -> Path:
    """`--validator` 는 *게이트 스크립트 경로*다 — fresh 검증자 에이전트 이름이 아니다.

    하네스 문맥에서 "검증자"는 plan-verifier 를 강하게 연상시켜, 라벨을 넘겼다가
    경로 해석 실패로 승인이 죽는 일이 있었다(2026-09-22 스테이징 스모크 관측).
    원인을 에러가 직접 말하게 한다.
    """
    if value is None:
        return default_validator()
    candidate = value.expanduser()
    if not candidate.exists():
        raise ValueError(
            f"--validator 는 게이트 스크립트 경로다(기본 validate_plan_gate.py) — "
            f"{value} 를 찾지 못했다. fresh 검증자 에이전트(plan-verifier 등)를 "
            f"가리키려던 것이면 이 플래그가 아니다 — 생략하면 기본 게이트가 돈다."
        )
    return candidate


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
    chained_from: str | None = None,
    fanout: list[str] | None = None,
    fanned_from: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if fanout and fanned_from:
        raise ValueError("--fanout(메인의 갈래 목록)과 --fanned-from(갈래의 자기 승인)은 같이 줄 수 없다")
    plan = plan.resolve()
    run_validator(plan, validator.resolve())
    steps = step_records(plan.read_text(encoding="utf-8", errors="replace"))
    if len(steps) < 2:
        raise ValueError("approved continuous plan must contain at least two top-level steps")

    if fanout:
        check_fanout_list(fanout, plan.read_text(encoding="utf-8", errors="replace"))

    state_path = root / ".harness" / "work.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        state = {"schema_version": 1, "active_work_id": None, "works": {}}
    if not isinstance(state, dict) or not isinstance(state.get("works"), dict):
        raise ValueError(".harness/work.json must use the canonical map-based works schema")
    approved_by = "user"
    if chained_from:
        if chain:
            raise ValueError("--chained-from 은 앞 영수증의 chain 을 승계한다 — --chain 과 같이 줄 수 없다")
        chain = check_chain_authority(state, chained_from, milestone_id, plan)
        approved_by = f"chain:{chained_from}"
    if fanned_from:
        if chained_from or chain:
            raise ValueError("--fanned-from 은 --chain·--chained-from 과 같이 줄 수 없다")
        check_fanout_authority(root, fanned_from, milestone_id, plan)
        approved_by = f"fanout:{fanned_from}"

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
            "approved_by": approved_by,
            "approved_at": approved_at,
            "plan_sha256": plan_fingerprint(plan),
            **({"chain": chain} if chain else {}),
            **({"fanout": fanout} if fanout else {}),
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
    state["works"][work_id] = work
    # M9 (D2, 2026-09-02): 포인터를 무조건 덮으면 같은 회차의 첫 승인이 훅·Stop 게이트·
    # continuation 에서 통째로 사라진다(2026-09-02 ui-dictionary 실측). 현재 포인터가
    # 아직 이어갈 수 있는 work 를 가리키면 그대로 두고, 실행 세션이 resume 으로 가져간다(D3).
    pointer = state.get("active_work_id")
    pointed = state["works"].get(pointer) if isinstance(pointer, str) else None
    keep_pointer = (
        isinstance(pointed, dict)
        and pointer != work_id
        and any(item.get("work_id") == pointer for item in continuable_works(state))
    )
    if not keep_pointer:
        state["active_work_id"] = work_id
    atomic_write_json(state_path, state)
    # 「다른 승인」 고지는 포인터 유지 여부와 무관하다 (2026-09-02 코드 리뷰 지적 4):
    # 포인터가 terminal 이어도 살아 있는 승인이 남아 있을 수 있고, 발사 프롬프트는
    # 이 줄의 부재를 "다른 승인 없음"으로 읽는다(harness-plan/SKILL.md).
    others = sorted(
        str(item.get("work_id"))
        for item in continuable_works(state)
        if item.get("work_id") != work_id
    )
    if others:
        head = (
            f"active_work_id 유지({pointer}) — 실행 세션이 resume 으로 가져간다."
            if keep_pointer
            else f"active_work_id → {work_id} (직전 포인터는 종결 상태)."
        )
        print(f"{head} 이 회차의 다른 승인: [{', '.join(others)}]")
    # h-e M32 (2026-09-05 D10): 승인 root 가 cwd 레포와 다르면 이 세션의 초점을 root 로 둔다 —
    # 훅·스킬 문서가 cwd 대신 소유 레포를 보게 하는 유일한 자동 진입점. 세션 키가 없으면(Codex 등)
    # 조용히 건너뛴다 — 초점은 보조이고 승인 자체를 막지 않는다.
    _maybe_set_focus(root, work_id, session_id)
    return work


OPEN_USER_DECISION = "사용자 몫 미결"


def _section(text: str, title: str) -> str | None:
    match = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else None


def check_chain_authority(state: dict[str, Any], chained_from: str, milestone_id: str, plan: Path) -> list[str]:
    """목표 승인(chain)으로 다음 milestone 계획을 승인해도 되는지 (M23, 2026-10-26).

    둘 다 만족해야 한다 — 아니면 경계에서 멈추고 사용자에게 간다:
      ① 앞 work 영수증의 chain 에 이 milestone 이 있다(목표 범위 안)
      ② 결정 로그에 「사용자 몫 미결」 결정이 남지 않았다
    (구 「plan-verifier 처분 필수」는 2026-11-16 사용자 결정으로 폐지 — 연쇄 계획 검증자는 막지 않는
    참고용이었고 반영률 97% 라 정지 조건이 못 됐다. 품질은 실행 중 빨강→초록과 마감이 맡는다.)
    통과하면 앞 영수증의 chain 을 그대로 돌려준다(다음 경계도 같은 목표로 이어지게).
    """
    prev = state["works"].get(chained_from)
    approval = prev.get("approval") if isinstance(prev, dict) else None
    chain = approval.get("chain") if isinstance(approval, dict) else None
    if not isinstance(chain, list) or not chain:
        raise ValueError(f"--chained-from {chained_from}: 그 work 영수증에 목표 chain 이 없다")
    if milestone_id.strip().lower() not in {str(item).strip().lower() for item in chain}:
        raise ValueError(f"{milestone_id} 는 목표 chain {chain} 밖이다 — 범위 밖 추가는 사용자 승인으로")
    text = plan.read_text(encoding="utf-8", errors="replace")
    decisions = _section(text, "결정 로그") or ""
    if OPEN_USER_DECISION in decisions:
        raise ValueError(f"결정 로그에 「{OPEN_USER_DECISION}」 결정이 남았다 — 경계에서 사용자에게 묻는다")
    return [str(item) for item in chain]


FANOUT_PACKET = Path(".harness") / "fanout" / "branch.json"
FANOUT_ID = re.compile(r"[a-z0-9-]+")


def plan_branch_ids(plan_text: str) -> set[str] | None:
    """계획서 `## 갈래 목록` 절의 갈래 id 집합(절이 없으면 None). 행 문법의 정본은 게이트
    (`validate_plan_gate.parse_fanout_rows`) 하나다 — 사본을 두지 않는다. 문법 밖 행은 승인 전에 게이트가 FAIL 시킨다."""
    import validate_plan_gate  # noqa: PLC0415 — 같은 디렉터리(위 sys.path)

    if validate_plan_gate._fanout_section(plan_text) is None:
        return None
    return {row[0] for row in validate_plan_gate.parse_fanout_rows(plan_text)}


def check_fanout_list(fanout: list[str], plan_text: str) -> None:
    """메인 승인의 `--fanout` 검사 (M26 코드 리뷰): id 형식, 그리고 계획서에 갈래 목록 절이 있으면 집합 일치."""
    bad = [item for item in fanout if not FANOUT_ID.fullmatch(item)]
    if bad:
        raise ValueError(f"--fanout: 갈래 id 는 [a-z0-9-]+ 여야 한다 — {bad}")
    listed = plan_branch_ids(plan_text)
    if listed is None:
        return
    given = set(fanout)
    missing, extra = sorted(listed - given), sorted(given - listed)
    if missing or extra:
        raise ValueError(
            f"--fanout 이 계획서 ## 갈래 목록 과 다르다 — 빠진 것(목록엔 있고 --fanout 엔 없음): {missing} · "
            f"남는 것(--fanout 엔 있고 목록엔 없음): {extra}"
        )


def _same_path(a: str, b: Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(b.resolve()))


def check_fanout_authority(root: Path, fanned_from: str, milestone_id: str, plan: Path) -> str:
    """갈래가 자기 계획서를 스스로 승인해도 되는지 (M26, 2026-11-18).

    권한의 근거는 **메인 영수증의 갈래 목록 하나뿐**이다 — 갈래 워크트리의 전달물
    (`.harness/fanout/branch.json`)이 가리키는 `main_root` 의 `.harness/work.json` 에서
    `works[<fanned_from>].approval.fanout` 를 읽어 이 갈래 id 가 있을 때만 통과한다.
    전부 만족해야 한다 — 아니면 그 탭에서 사용자에게 묻는다:
      ① 전달물이 있고 `main_work_id`·`milestone_id` 가 인자와 같다
      ② 메인 영수증의 fanout 목록에 전달물의 `branch_id` 가 있다
      ③ 살아 있는 권한 — 메인 work `status` 가 active, 메인 등록부(`.harness/fanout/<메인 work-id>.json`)에
         id 가 같고 `worktree_path` 가 이 `--root` 와 같은 경로(resolve 후 정규화 비교)인 항목이 `running`
      ④ 결정 로그에 「사용자 몫 미결」 결정이 남지 않았다(연쇄와 같은 규칙)
    통과하면 branch_id 를 돌려준다.
    """
    packet_path = root / FANOUT_PACKET
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"--fanned-from: 갈래 전달물 {FANOUT_PACKET.as_posix()} 이 없다 — 갈래 워크트리에서만 쓴다") from exc
    if not isinstance(packet, dict):
        raise ValueError("--fanned-from: 갈래 전달물이 JSON 객체가 아니다")
    if packet.get("main_work_id") != fanned_from:
        raise ValueError(f"--fanned-from {fanned_from}: 전달물의 main_work_id 는 {packet.get('main_work_id')!r} 다")
    if str(packet.get("milestone_id", "")).strip().lower() != milestone_id.strip().lower():
        raise ValueError(f"--milestone-id {milestone_id}: 전달물의 milestone_id 는 {packet.get('milestone_id')!r} 다")
    branch_id = str(packet.get("branch_id") or "").strip()
    main_root = Path(str(packet.get("main_root") or ""))
    if not branch_id or not str(main_root):
        raise ValueError("--fanned-from: 전달물에 branch_id·main_root 가 없다")
    try:
        main_state = json.loads((main_root / ".harness" / "work.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"--fanned-from: 메인 영수증을 읽지 못했다 ({main_root}) — {exc}") from exc
    main_work = (main_state.get("works") or {}).get(fanned_from) if isinstance(main_state, dict) else None
    approval = main_work.get("approval") if isinstance(main_work, dict) else None
    listed = approval.get("fanout") if isinstance(approval, dict) else None
    if not isinstance(listed, list) or branch_id not in [str(item) for item in listed]:
        raise ValueError(
            f"갈래 {branch_id} 는 메인 {fanned_from} 영수증의 갈래 목록 {listed or []} 에 없다 — 목록 밖 갈래는 사용자 승인으로"
        )
    if main_work.get("status") != "active":
        raise ValueError(
            f"메인 {fanned_from} 의 status 는 {main_work.get('status')!r} 다 — active 일 때만 갈래가 자기 승인한다"
        )
    registry_path = main_root / ".harness" / "fanout" / f"{fanned_from}.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"--fanned-from: 메인 등록부를 읽지 못했다 ({registry_path}) — {exc}") from exc
    entries = registry.get("branches") if isinstance(registry, dict) else None
    entry = next(
        (
            b for b in (entries if isinstance(entries, list) else [])
            if isinstance(b, dict) and b.get("id") == branch_id and _same_path(str(b.get("worktree_path") or ""), root)
        ),
        None,
    )
    if entry is None:
        raise ValueError(
            f"메인 등록부({registry_path.name})에 id={branch_id} 이면서 worktree_path 가 이 루트({root})인 항목이 없다"
        )
    if entry.get("state") != "running":
        raise ValueError(f"등록부의 갈래 {branch_id} state 는 {entry.get('state')!r} 다 — running 일 때만 자기 승인한다")
    text = plan.read_text(encoding="utf-8", errors="replace")
    if OPEN_USER_DECISION in (_section(text, "결정 로그") or ""):
        raise ValueError(f"결정 로그에 「{OPEN_USER_DECISION}」 결정이 남았다 — 그 탭에서 사용자에게 묻는다")
    return branch_id


def _maybe_set_focus(root: Path, work_id: str, session_id: str) -> None:
    session = harness_focus.session_key() or harness_focus.session_key(session_id)
    if session is None:
        return
    try:
        cwd_root = Path.cwd().resolve()
    except OSError:
        return
    if root == cwd_root or root in cwd_root.parents:
        return
    rc = harness_focus.main(["set", "--root", str(root), "--work-id", work_id, "--session", session])
    if rc != 0:
        print("focus: set 실패 — 승인은 유효, 초점만 수동 (harness_focus.py set)", file=sys.stderr)


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
    parser.add_argument("--validator", type=Path,
                        help="게이트 스크립트 경로(기본: validate_plan_gate.py). "
                             "fresh 검증자 에이전트 이름이 아니다.")
    parser.add_argument("--approved-at", default=date.today().isoformat())
    parser.add_argument(
        "--chained-from",
        default=None,
        help=(
            "목표 승인으로 이어지는 다음 milestone 계획을 승인한다(M23). 값 = 앞 milestone 의 "
            "work-id. 그 영수증 chain 에 이 milestone 이 있고, "
            "결정 로그에 「사용자 몫 미결」 이 없을 때만 통과 — approved_by=chain:<work-id>."
        ),
    )
    parser.add_argument(
        "--chain",
        default=None,
        help=(
            "승인 게이트에서 사용자에게 제시하고 함께 승인받은 후속 milestone id 목록"
            "(쉼표 구분). 여기 기록된 것만 next-chained 무개입 연쇄 후보가 된다 — "
            "사용자에게 보여주지 않은 id 를 적으면 안 된다."
        ),
    )
    parser.add_argument(
        "--fanout",
        default=None,
        help=(
            "펼치는 계획(M26): 메인 승인 때 사용자에게 제시하고 함께 승인받은 갈래 id 목록"
            "(쉼표 구분). 영수증 approval.fanout 에 남고, 갈래의 --fanned-from 자기 승인의 유일한 근거다."
        ),
    )
    parser.add_argument(
        "--fanned-from",
        default=None,
        help=(
            "갈래 워크트리에서 자기 계획서를 승인한다(M26). 값 = 메인 work-id. 전달물 "
            ".harness/fanout/branch.json 의 main_root 영수증 fanout 목록에 이 갈래 id 가 있고 "
            "결정 로그에 「사용자 몫 미결」 이 없을 때만 통과 — approved_by=fanout:<메인 work-id>."
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
            validator=resolve_validator(args.validator),
            approved_at=args.approved_at,
            chain=parse_chain(args.chain),
            chained_from=args.chained_from,
            fanout=parse_chain(args.fanout),
            fanned_from=args.fanned_from,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"approval gate: FAIL — {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "approved", "work": work}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
