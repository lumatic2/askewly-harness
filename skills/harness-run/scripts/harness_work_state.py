#!/usr/bin/env python3
"""Inspect the lightweight harness continuation state.

This is a small Boulder-inspired reader for `.harness/work.json`.
It does not auto-continue sessions or mutate files; it only validates the
current active-work pointer and derives plan checklist progress.

거처 (FA1 step-4, 2026-07-24): **여기가 정본이다** — 구 정본 `the-source-repo/scripts/`
는 로더 shim 으로 남아 이 파일을 불러 쓴다("기계장치는 한 곳"). `~/.codex/hooks/` 사본은
`the-source-repo/scripts/deploy_codex_hooks.py` 가 여기서 출고한다(훅 한 벌 import 용).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_REL = Path(".harness") / "work.json"
CONTINUABLE_STATUSES = {"active", "paused"}
TERMINAL_STATUSES = {"completed", "abandoned"}
COUNTED_HEADINGS = {"Step 트리", "Step Tree", "TODOs", "Final Verification Wave"}

# 문서화된 정지 사유 → stop_detail 의 canonical 필드. continuation hook 과 diagnose 가
# 같은 판정을 하도록 여기가 단일 출처다 (HQ1 step-1, 2026-07-21 — 구 hook 로컬 정의 이동).
STOP_DETAIL_FIELDS = {
    "blocked": "evidence",
    "decision_required": "decision_id",
    "risk_gate": "risk_id",
    "secret_required": "requirement",
    "external_authority_required": "requirement",
    "user_stopped": "user_instruction",
}


def normalize_session_token(raw: Any, runtime: str = "claude") -> str | None:
    """Stop payload 의 불투명 UUID 든 `<runtime>:<uuid>` 든 durable token 으로 정규화."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    return value if ":" in value else f"{runtime}:{value}"


def token_owns_work(token: str | None, work: dict[str, Any], runtime: str = "claude") -> bool:
    """cs#241 정확 소유 바인딩 + runtime-family fallback (hook 에서 이동 — 단일 출처)."""
    if token is None:
        return False
    bound = work.get("owner_session_uuid")
    if isinstance(bound, str) and bound.strip():
        return token == bound.strip()
    session_ids = work.get("session_ids")
    if not isinstance(session_ids, list):
        return False
    owners = {str(item) for item in session_ids}
    if token in owners:
        return True
    prefix = f"{runtime}:"
    return token.startswith(prefix) and any(owner.startswith(prefix) for owner in owners)


def stop_detail_text(reason: Any, detail: Any) -> str:
    """stop_detail 에서 증거 텍스트 추출 — canonical 필드 우선, non-empty 문자열 fallback."""
    if not isinstance(detail, dict):
        return ""
    field = STOP_DETAIL_FIELDS.get(str(reason), "")
    value = detail.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    for fallback in detail.values():
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
    return ""


def allowed_hard_stop(work: dict[str, Any], checklist_remaining: int) -> bool:
    """문서화된 정지(hard stop)로 인정되는가 (hook 에서 이동 — 단일 출처)."""
    reason = work.get("stop_reason")
    allowed = work.get("allowed_stop_reasons")
    if not isinstance(reason, str) or not isinstance(allowed, list) or reason not in allowed:
        return False
    if reason == "completed":
        return work.get("status") == "completed" and checklist_remaining == 0
    return bool(stop_detail_text(reason, work.get("stop_detail")))


@dataclass(frozen=True)
class Checklist:
    completed: int
    remaining: int
    total: int
    next_task_label: str | None
    # 지금 **동시에** 착수 가능한 미완 leaf 들 (2026-07-23 OI2). 그래프가 없거나 깨졌으면
    # 빈 목록이고, 그때 `next_task_label` 이 텍스트 순서의 첫 미완 leaf 로 폴백한다.
    ready_labels: tuple[str, ...] = ()


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


# milestone/horizon 이 완료되면 계획 문서는 `plans/` → `archive/` 로 옮겨진다.
# 그때 work.json 의 plan_path 는 그대로 남아 조용히 끊겼다(2026-07-22: 한 번에
# 7건 발견). 이동 시점에 게이트를 하나 더 세우는 대신, 읽는 쪽에서 짝을 찾아본다.
# 부재를 삼키지는 않는다 — 어느 쪽에도 없으면 원래 경로를 그대로 돌려준다.
_ARCHIVE_PAIRS: tuple[tuple[str, str], ...] = (
    ("plans/horizons/", "archive/horizons/"),
    ("plans/", "archive/plans/"),
)


def archive_variants(value: str) -> list[str]:
    """`plans/` ↔ `archive/` 짝 경로 후보. 더 구체적인 접두를 먼저 본다."""
    posix = value.replace("\\", "/")
    for live, archived in _ARCHIVE_PAIRS:
        if posix.startswith(live):
            return [archived + posix[len(live):]]
        if posix.startswith(archived):
            return [live + posix[len(archived):]]
    return []


def resolve_repo_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if resolved.exists() or Path(value).is_absolute():
        return resolved
    for candidate in archive_variants(value):
        alternative = (root / candidate).resolve()
        if alternative.exists():
            return alternative
    return resolved


def parse_level_two_heading(line: str) -> str | None:
    if not line.startswith("## "):
        return None
    return line[3:].strip()


def parse_top_level_checkbox(line: str) -> tuple[bool, str] | None:
    if line.startswith("- [ ] "):
        return False, line[len("- [ ] "):].strip()
    if line.startswith("- [x] ") or line.startswith("- [X] "):
        return True, line[len("- [x] "):].strip()
    return None


def _load_plan_gate():
    """`validate_plan_gate` 를 배포 위치에서 찾아 import 한다 (2026-07-23 OI2 step-4).

    **의존 문법 파서를 여기 복사하지 않는다.** 같은 사실이 두 벌이면 어긋난다는 것이
    직전 horizon(`single-source-harness`) 전체의 결론이고, 실제로 이 파서는 한 번 어긋나
    계획서의 1/5 를 거절하는 상태로 조용히 있었다(cs#375). 파서는 게이트 한 곳에만 산다.

    못 찾으면 `None` — 소비자는 텍스트 순서로 폴백한다. 훅은 import 실패로 죽지 않는다.
    """
    for base in (Path.home() / ".codex", Path.home() / ".claude"):
        # 2026-07-23 재조립 P5: 기계장치 정본은 harness-run 스킬 scripts/ (구 harness 은퇴)
        candidate = base / "skills" / "harness-run" / "scripts" / "validate_plan_gate.py"
        if not candidate.is_file():
            continue
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("_harness_plan_gate", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            if hasattr(module, "derive_waves"):
                return module
        except Exception:
            continue
    return None


def leaf_id_of(label: str) -> str | None:
    """`**step-2 — slug**` 같은 체크박스 라벨에서 leaf id 를 뽑는다."""
    match = re.search(r"step-\d+", label or "")
    return match.group(0) if match else None


def plan_ready_leaves(plan_path: Path, done_ids: set[str]) -> list[str]:
    """의존이 **전부 끝난** 미완 leaf 들. 그래프가 없으면 빈 목록.

    "다음 할 일"이 텍스트 순서가 아니라 자료구조에서 나오게 하는 자리다. 계획서에
    순서만 있고 의존이 없으면 경계마다 멈출 구실이 생긴다 — cs#358 이 continuation
    단위를 milestone→horizon 으로 올려 증상은 막았지만 근거는 여전히 텍스트 순서였다.
    """
    gate = _load_plan_gate()
    if gate is None:
        return []
    try:
        text = plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    waves = gate.derive_waves(text)
    if not waves:
        return []
    labels = {}
    for match in gate.LEAF_ID_HEADING.finditer(text):
        labels[match.group("id")] = f"{match.group('id')} — {match.group('slug')}".strip()
    for wave in waves:
        pending = [leaf for leaf in wave if leaf not in done_ids]
        if pending:
            return [labels.get(leaf, leaf) for leaf in pending]
    return []


def get_plan_checklist(plan_path: Path) -> Checklist:
    try:
        lines = plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return Checklist(completed=0, remaining=0, total=0, next_task_label=None)

    has_counted_sections = any(parse_level_two_heading(line) in COUNTED_HEADINGS for line in lines)
    in_counted_section = not has_counted_sections
    completed = 0
    remaining = 0
    next_task_label: str | None = None
    done_ids: set[str] = set()
    for line in lines:
        heading = parse_level_two_heading(line)
        if heading is not None:
            in_counted_section = heading in COUNTED_HEADINGS
            continue
        if not in_counted_section:
            continue
        checkbox = parse_top_level_checkbox(line)
        if checkbox is None:
            continue
        is_checked, label = checkbox
        if is_checked:
            completed += 1
            leaf = leaf_id_of(label)
            if leaf:
                done_ids.add(leaf)
        else:
            remaining += 1
            next_task_label = next_task_label or label
    ready = plan_ready_leaves(plan_path, done_ids) if remaining else []
    return Checklist(completed=completed, remaining=remaining, total=completed + remaining,
                     next_task_label=(ready[0] if ready else next_task_label),
                     ready_labels=tuple(ready))


def sync_steps_from_plan(work: dict[str, Any], plan_path: Path) -> int:
    """plan 체크박스 → work.json steps 상태 반영. 반영한 step 수를 돌려준다.

    CF6 (2026-07-22): step 진행 상태의 소스가 둘이었다 — plan 의 체크박스와
    `work.json` 의 `steps[]`. 그런데 `steps[]` 를 갱신하는 경로가 approve(생성)와
    report_close(전체 완료)뿐이라, **중간 진행이 어디에도 기록되지 않았다.**
    Stop hook 은 `steps[]` 를 읽으므로 milestone 절반을 끝내도 "next: step-1" 이라고
    보고했고, 컨텍스트가 끊긴 뒤 재개하면 처음부터 다시 하게 된다.
    승인 해시는 체크박스 *상태*를 봉인하지 않으므로(MM7) plan 을 소스로 삼는다.
    """
    steps = work.get("steps")
    if not isinstance(steps, list) or not steps:
        return 0
    done_labels = set()
    try:
        lines = plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    for line in lines:
        checkbox = parse_top_level_checkbox(line)
        if checkbox and checkbox[0]:
            done_labels.add(checkbox[1])
    changed = 0
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "")
        # 승인 시 기록된 label 과 plan 본문 label 은 같은 문자열에서 파생된다.
        hit = any(label and (label in d or d in label) for d in done_labels)
        current = raw.get("status", "pending")
        if hit:
            want = "completed"
        elif current == "completed":
            # plan 이 원본이므로 체크가 풀렸으면 완료 주장도 내려간다(2026-07-22).
            # 낡은 completed 를 그대로 두면 "완료됐다는데 계획서엔 안 됐다" 가 남는다.
            want = "pending"
        else:
            # blocked·error 는 plan 체크박스가 표현하지 못하는 정보라 보존한다.
            want = current
        if raw.get("status") != want:
            raw["status"] = want
            changed += 1
    return changed


def get_runtime_checklist(work: dict[str, Any], plan_path: Path) -> Checklist:
    """진행 상태는 **언제나 plan 체크박스에서 파생**한다 (2026-07-22 사용자 확정).

    계획서는 사람이 읽는 산출물이 아니라 **에이전트가 보면서 자기 진행을 체크·기록하는
    장부**다. 따라서 체크박스가 진행의 원본이고 `steps[]` 는 승인 때 박힌 *명단*(id·label)일
    뿐이다.

    이전 구현은 `steps[]` 의 저장된 status 를 먼저 믿고 plan 은 fallback 으로만 봤다. 그래서
    `steps[]` 를 갱신하는 경로(approve·수동 sync)를 지나지 않은 진행은 전부 유실됐고,
    `report_close` 로 완료된 work 가 "완료" 이면서 동시에 "next: step-2" 라고 말하는 상태가
    남았다(2026-07-22 실측). **읽는 쪽에서 매번 파생하면 어느 쓰기 경로가 빠뜨려도 어긋나지
    않는다** — 동기화를 잊을 수 있는 지점 자체를 없앤다.
    """
    steps = work.get("steps")
    if not isinstance(steps, list) or not steps:
        return get_plan_checklist(plan_path)
    # 명단은 work.json 에서, 진행은 plan 에서 — 읽기 시점에 항상 맞춘다(in-memory).
    sync_steps_from_plan(work, plan_path)
    completed = 0
    remaining = 0
    next_task_label: str | None = None
    done_ids: set[str] = set()
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("id") or "unnamed step")
        if raw.get("status") == "completed":
            completed += 1
            leaf = leaf_id_of(str(raw.get("id") or "")) or leaf_id_of(label)
            if leaf:
                done_ids.add(leaf)
        else:
            remaining += 1
            next_task_label = next_task_label or label
    # 명단은 work.json, 진행은 plan, **다음 할 일은 그래프**에서 (2026-07-23 OI2).
    ready = plan_ready_leaves(plan_path, done_ids) if remaining else []
    return Checklist(completed=completed, remaining=remaining, total=completed + remaining,
                     next_task_label=(ready[0] if ready else next_task_label),
                     ready_labels=tuple(ready))


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# MM7 step-1 (2026-07-21): 승인 해시는 계획 **본문**을 봉인해야지, step 체크박스를
# 켜는 정상 진행까지 변조로 잡으면 안 된다. 상태 마커만 중립화하고 그 줄의 텍스트를
# 포함한 나머지는 그대로 봉인한다.
# ~~이 정규화는 작성자(approve_harness_plan.py)와 반드시 동일해야 한다~~ — **폐지
# (2026-07-24 FA1 step-4)**: 주석으로만 묶인 사본 계약은 언젠가 어긋난다. 이제
# approve_harness_plan.py 가 여기 있는 `normalize_plan_text` 를 import 한다 — 구현 1개.
#
# CF3 step-3 (2026-07-21): 봉인 대상은 **계획의 내용**이지 그 표현이 아니다. 줄바꿈
# 방식(CRLF/LF)과 행말 공백은 `.gitattributes` 대량 정규화·에디터 설정만으로 바뀌는데,
# 그때마다 승인이 깨져 continuation 이 막혔다(2026-07-21 실사고, 이틀 이월).
# 절차에 "정규화 후 재승인" 단계를 더하는 건 이 horizon 이 없애려는 대리형 장치이므로,
# 표현 차이를 해시 단계에서 흡수한다. 본문 텍스트 변경은 여전히 전부 검출된다.
CHECKBOX_STATE_RE = re.compile(r"^(\s*[-*]\s*)\[[ xX]\]", re.M)

# 2026-07-22 사용자 확정 — 계획서는 *에이전트가 보면서 자기 진행을 체크·기록하며
# 나아가는 장부*다. 그런데 템플릿이 `## finding 큐`·`## 진행 로그(append-only)` 를
# 두고 실행 중 적으라고 하면서, 승인 해시는 본문 전체를 봉인해 그 기록을 변조로
# 잡았다(SS1 step-3 에서 실제로 차단 — finding F1 을 적자마자 continuation FAIL).
# 지시문 자기모순이므로 MM7(체크박스 상태 제외)과 같은 방식으로 해소한다:
# **append-only 로 선언된 절의 내용은 봉인 대상이 아니다.** 제목 줄은 남기므로
# 그 절을 지우거나 이름을 바꾸는 것은 여전히 검출된다.
APPEND_ONLY_SECTIONS = ("finding 큐", "진행 로그")
APPEND_ONLY_RE = re.compile(
    r"^(##\s+(?:" + "|".join(re.escape(s) for s in APPEND_ONLY_SECTIONS) + r")[^\n]*\n)"
    r".*?(?=^##\s|\Z)",
    re.M | re.S,
)


def normalize_plan_text(text: str) -> str:
    text = CHECKBOX_STATE_RE.sub(r"\1[ ]", text)
    text = APPEND_ONLY_RE.sub(r"\1", text)
    # 줄바꿈 통일 → 행말 공백 제거 → 파일 끝 빈 줄 통일. 표현만 흡수한다.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n") + "\n"


def plan_fingerprint(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return hashlib.sha256(normalize_plan_text(text).encode("utf-8")).hexdigest()


def approval_errors(work: dict[str, Any], plan_path: Path | None) -> list[str]:
    errors: list[str] = []
    if work.get("execution_mode") != "continuous":
        errors.append("execution_mode must be continuous")
    approval = work.get("approval")
    if not isinstance(approval, dict):
        return errors + ["approval receipt is missing"]
    for field in ("approved_by", "approved_at", "plan_sha256"):
        if not isinstance(approval.get(field), str) or not approval[field].strip():
            errors.append(f"approval.{field} is missing")
    expected = approval.get("plan_sha256")
    if isinstance(expected, str) and plan_path is not None:
        # 정규화 해시가 정본. raw 파일 해시도 받아주는 건 MM7 이전에 바인딩된
        # 승인(legacy)을 재승인 없이 계속 쓰기 위해서다.
        accepted = {plan_fingerprint(plan_path), file_sha256(plan_path)} - {None}
        # 2026-08-06 감사 #2: 후보가 비면(계획서가 사라졌거나 읽을 수 없음) 비교를 통째로
        # 건너뛰어 **계획서 없는 영수증이 승인 통과**했다(재현됨: 계획 삭제 후
        # require_approval → True). 읽을 수 없는 것은 "일치"가 아니다 — fail-closed.
        if not accepted:
            errors.append(f"approved plan is unreadable or missing: {plan_path}")
        elif expected not in accepted:
            errors.append("approved plan hash does not match current plan")
    return errors


def works_all_terminal(works: Any) -> bool:
    """True if every work entry has a terminal status (or there are none).

    Used to recognize the normal idle state between milestones: no active
    work pointer, and nothing left in a non-terminal (active/paused) state.
    An unrecognized `works` structure (not dict/list/None) is treated as
    non-terminal (fail-closed).
    """
    if works is None:
        return True
    if isinstance(works, dict):
        items = works.values()
    elif isinstance(works, list):
        items = works
    else:
        return False
    for item in items:
        if not isinstance(item, dict) or item.get("status") not in TERMINAL_STATUSES:
            return False
    return True


# SS2 앞선 수리 (2026-07-22): continuation 상태의 단위가 **milestone** 이라, milestone 이
# 닫히는 순간 hook 이 정지를 허용해 왔다. 그런데 승인의 단위는 CS6(2026-07-17) 이후로
# **계획 전체 연쇄**다 — 사용자는 SS1~SS4 를 한 번에 승인하고 무감독 진행을 기대하는데,
# 기계는 SS1 이 끝나면 매번 멈췄다(실측: 이 horizon 에서 SS1 종료 직후 hook 무출력).
# "연쇄로 간다"는 약속이 SKILL.md 산문에만 있었고 턴 경계에서 산문은 진다.
# 그래서 완료 시점에 **다음 milestone 이 이미 계획서까지 있는지**를 본다.
# ~~계획서 존재 = "승인 연쇄에 들어있다"는 관측 가능한 증거~~ — **폐기 (2026-07-24 FA1 step-1).**
# 계획서가 plans/ 에 있다는 것과 사용자가 그 계획을 승인했다는 것은 다른 사실이다 —
# 승인 전 초안도 plans/ 에 산다. 그 등식이 미승인 초안을 무개입으로 승인·실행하는
# 구멍이었다(2026-07-24 흐름 감사 적발). 이제 연쇄 후보는 계획서 존재에 더해
# **사용자 승인 이력**(그 계획의 approve 영수증, 또는 승인 게이트에서 제시·승인돼
# 영수증에 기록된 chain 목록)을 요구한다 — bounded autonomy 는 user-approved spec
# 의 자율 실행이지 intent-setting 의 자율이 아니다(dryforge).
MILESTONE_MARKER_RE = re.compile(r"<!--\s*harness:milestone\s+(.*?)-->", re.S)
GOAL_MARKER_RE = re.compile(r"<!--\s*harness:goal\s+(.*?)-->", re.S)
MARKER_ATTR_RE = re.compile(r'([A-Za-z_][\w-]*)="([^"]*)"')
CHAINED_MILESTONE_STATUSES = {"pending", "active"}


def _marker_attrs(raw: str) -> dict[str, str]:
    return dict(MARKER_ATTR_RE.findall(raw))


def user_approved_milestones(state: Any) -> set[str]:
    """사용자 승인 이력이 있는 milestone id 집합 (소문자) — FA1 step-1 (2026-07-24).

    두 경로만 승인으로 인정한다:
      ① 그 milestone 의 work 에 approval receipt 가 실재한다 (approve_harness_plan 등록)
      ② 어느 work 의 receipt 든 `chain` 목록에 들어 있다 — 승인 게이트에서
         후속 milestone 목록을 사용자에게 제시하고 함께 승인받은 기록
    """
    approved: set[str] = set()
    works = state.get("works") if isinstance(state, dict) else None
    if not isinstance(works, dict):
        return approved
    for entry in works.values():
        if not isinstance(entry, dict):
            continue
        approval = entry.get("approval")
        if not isinstance(approval, dict):
            continue
        sha = approval.get("plan_sha256")
        if isinstance(sha, str) and sha.strip():
            milestone = str(entry.get("milestone_id") or "").strip().lower()
            if milestone:
                approved.add(milestone)
        chain = approval.get("chain")
        if isinstance(chain, list):
            approved.update(str(item).strip().lower() for item in chain if str(item).strip())
    return approved


def chained_candidates(
    root: Path, work: dict[str, Any], state: Any = None
) -> tuple[dict[str, str] | None, list[str]]:
    """(다음 연쇄 milestone, 승인 없어 건너뛴 후보 id 목록).

    2026-07-23 재조립 P4: 구현은 같고 **범위가 바뀌었다.** 이전에는 "같은 horizon 안에서"
    가 조건이었는데 horizon 층이 폐지됐다(C4·C9). 이제 ROADMAP 전체의 pending/active
    마커를 본다 — 연쇄 자체는 없애지 않는다. 무개입 진행이 이 하네스의 정체성이고(C1),
    죽은 것은 연쇄가 아니라 그 범위를 정하던 층이다.

    셋을 모두 만족할 때만 반환한다 — 하나라도 어긋나면 정지가 정상이다:
      ① ROADMAP 에 pending/active milestone 마커가 남았다
      ② 그 milestone 의 계획서가 `plans/` 에 살아 있다
         (`archive/` 로 옮겨진 완료 계획서는 후보가 아니다)
      ③ 사용자 승인 이력이 있다 (`user_approved_milestones` — FA1 step-1, 2026-07-24.
         미승인 초안은 후보가 아니라 `/harness-plan` 승인 게이트 대상이다)
    """
    roadmap = root / "ROADMAP.md"
    if not roadmap.is_file():
        return None, []
    try:
        text = roadmap.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, []
    plans_dir = root / "plans"
    if not plans_dir.is_dir():
        return None, []
    if state is None:
        state = read_json(root / STATE_REL)
    approved = user_approved_milestones(state)
    done_id = str(work.get("milestone_id") or "").strip().lower()
    unapproved: list[str] = []
    found: dict[str, str] | None = None
    for match in MILESTONE_MARKER_RE.finditer(text):
        attrs = _marker_attrs(match.group(1))
        milestone_id = attrs.get("id", "").strip()
        if not milestone_id or attrs.get("status") not in CHAINED_MILESTONE_STATUSES:
            continue
        if milestone_id.lower() == done_id:
            continue
        for plan in sorted(plans_dir.glob(f"*-{milestone_id.lower()}-*.md")):
            if milestone_id.lower() not in approved:
                unapproved.append(milestone_id)
                break
            if found is None:
                found = {
                    "milestone_id": milestone_id,
                    "plan_path": plan.relative_to(root).as_posix(),
                }
            break
    return found, unapproved


def next_chained_milestone(
    root: Path, work: dict[str, Any], state: Any = None
) -> dict[str, str] | None:
    """`chained_candidates` 의 매치만 — 기존 호출자(continuation hook) 호환 유지."""
    found, _ = chained_candidates(root, work, state)
    return found


def active_work(state: dict[str, Any]) -> dict[str, Any] | None:
    work_id = state.get("active_work_id")
    works = state.get("works")
    if isinstance(work_id, str) and isinstance(works, dict):
        work = works.get(work_id)
        return work if isinstance(work, dict) else None
    if isinstance(works, list):
        active = [item for item in works if isinstance(item, dict) and item.get("status") in CONTINUABLE_STATUSES]
        if len(active) != 1:
            return None
        raw = active[0]
        return {
            **raw,
            "work_id": raw.get("work_id") or raw.get("id"),
            "plan_path": raw.get("plan_path") or raw.get("plan"),
            "changeset_path": raw.get("changeset_path") or "<product-phase>",
        }
    return None


def build_status(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    state_path = root / STATE_REL
    if not state_path.exists():
        return {
            "schema_version": 1,
            "root": str(root),
            "state_path": str(state_path),
            "active_work": None,
            "checklist": Checklist(completed=0, remaining=0, total=0, next_task_label=None).__dict__,
            "summary": {"status": "pass", "checks": 1, "pass": 1, "warn": 0, "fail": 0},
            "checks": [
                {
                    "name": "state_file",
                    "status": "pass",
                    "message": "checkout-local work state is not initialized; no active work",
                    "detail": {"path": str(state_path), "initialized": False},
                }
            ],
        }

    state = read_json(state_path)
    checks: list[dict[str, Any]] = []
    if not isinstance(state, dict):
        return {
            "schema_version": 1,
            "root": str(root),
            "state_path": str(state_path),
            "summary": {"status": "fail", "checks": 1, "pass": 0, "warn": 0, "fail": 1},
            "checks": [
                {
                    "name": "state_file",
                    "status": "fail",
                    "message": "checkout-local .harness/work.json is invalid",
                    "detail": {"path": str(state_path), "initialized": True},
                }
            ],
        }

    checks.append(
        {
            "name": "schema_version",
            "status": "pass" if state.get("schema_version") in {None, 1} else "fail",
            "message": "schema_version is compatible" if state.get("schema_version") in {None, 1} else "schema_version must be 1",
            "detail": {"value": state.get("schema_version")},
        }
    )
    work = active_work(state)
    work_id = state.get("active_work_id")
    if work is not None:
        active_work_status, active_work_message = "pass", "active work resolves"
    elif not work_id and works_all_terminal(state.get("works")):
        active_work_status, active_work_message = "pass", "no active work (idle)"
    else:
        active_work_status, active_work_message = "fail", "active work does not resolve"
    checks.append(
        {
            "name": "active_work",
            "status": active_work_status,
            "message": active_work_message,
            "detail": {"active_work_id": work_id},
        }
    )

    checklist = Checklist(completed=0, remaining=0, total=0, next_task_label=None)
    if work is not None:
        status = str(work.get("status") or "")
        checks.append(
            {
                "name": "work_status",
                "status": "pass" if status in CONTINUABLE_STATUSES | TERMINAL_STATUSES else "fail",
                "message": f"work status is {status}" if status else "work status is missing",
                "detail": {"status": status},
            }
        )
        plan_path = resolve_repo_path(root, work.get("plan_path") if isinstance(work.get("plan_path"), str) else None)
        checks.append(
            {
                "name": "plan_path",
                "status": "pass" if plan_path is not None and plan_path.exists() else "fail",
                "message": "plan_path exists" if plan_path is not None and plan_path.exists() else "plan_path is missing",
                "detail": {"path": str(plan_path) if plan_path else None},
            }
        )
        if plan_path is not None:
            checklist = get_runtime_checklist(work, plan_path)
            expected_next = work.get("next_step")
            next_matches = (
                not isinstance(expected_next, str)
                or checklist.next_task_label is None
                or expected_next in checklist.next_task_label
            )
            checks.append(
                {
                    "name": "plan_checklist",
                    "status": "pass" if checklist.total > 0 else "warn",
                    "message": f"plan checklist has {checklist.remaining}/{checklist.total} remaining",
                    "detail": checklist.__dict__,
                }
            )
            checks.append(
                {
                    "name": "next_step_hint",
                    "status": "pass" if next_matches else "warn",
                    "message": "next_step is consistent with plan" if next_matches else "next_step does not match first unchecked checkbox",
                    "detail": {"next_step": expected_next, "next_task_label": checklist.next_task_label},
                }
            )
            if status in CONTINUABLE_STATUSES and checklist.remaining == 0:
                checks.append(
                    {
                        "name": "continuable_remaining",
                        "status": "warn",
                        "message": "work is continuable but plan has no remaining top-level checkboxes",
                        "detail": {"status": status},
                    }
                )
        if status in CONTINUABLE_STATUSES:
            receipt_errors = approval_errors(work, plan_path)
            checks.append(
                {
                    "name": "approval_receipt",
                    "status": "pass" if not receipt_errors else "fail",
                    "message": "approval receipt matches immutable plan" if not receipt_errors else "; ".join(receipt_errors),
                    "detail": {"errors": receipt_errors},
                }
            )

    summary = {
        "status": worst_status([check["status"] for check in checks]),
        "checks": len(checks),
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "warn": sum(1 for check in checks if check["status"] == "warn"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
    }
    return {
        "schema_version": 1,
        "root": str(root),
        "state_path": str(state_path),
        "active_work": work,
        "checklist": checklist.__dict__,
        "summary": summary,
        "checks": checks,
    }


def is_linked_worktree(root: Path) -> bool:
    """linked git worktree = `<root>/.git` 이 gitdir 포인터 *파일* (메인 체크아웃은 디렉터리)."""
    return (root / ".git").is_file()


def diagnose(root: Path, token: str | None, runtime: str = "claude") -> dict[str, Any]:
    """이 루트에서 continuation 이 발화하지 않는 이유를 판정한다 (HQ1 step-1).

    continuation hook 의 build_decision 과 같은 판정 함수(token_owns_work·
    allowed_hard_stop)를 공유해 진단이 실제 동작과 어긋날 수 없게 한다.
    reason: no-work-json / no-active-work / not-continuable / not-owner /
            remaining-0 / honored-stop / ok
    """
    root = root.resolve()
    state_path = root / STATE_REL
    worktree = is_linked_worktree(root)
    if not state_path.exists():
        hint = (
            " 이 루트는 linked worktree 입니다 — work.json 은 checkout-local 이라 이 워크트리에서"
            " approve_harness_plan.py 를 다시 돌려야 continuation 이 붙습니다 (cs#248 모델)."
            if worktree
            else " 이 루트에서 approve_harness_plan.py 로 계획을 승인해야 continuation 이 붙습니다."
        )
        return {"reason": "no-work-json", "message": f"continuation 침묵: .harness/work.json 없음.{hint}", "worktree": worktree}
    state = read_json(state_path)
    work = active_work(state) if isinstance(state, dict) else None
    if work is None:
        return {"reason": "no-active-work", "message": "continuation 침묵: active work 없음 (승인된 작업이 없거나 전부 종결).", "worktree": worktree}
    status = str(work.get("status") or "")
    if status not in CONTINUABLE_STATUSES:
        return {"reason": "not-continuable", "message": f"continuation 침묵: active work {work.get('work_id')} 상태가 {status or '<없음>'}.", "worktree": worktree}
    if not token_owns_work(token, work, runtime):
        owner = work.get("owner_session_uuid") or f"session_ids={work.get('session_ids')}"
        return {
            "reason": "not-owner",
            "message": (
                f"continuation 침묵: 현 세션({token or '<토큰 없음>'})이 active work {work.get('work_id')} 의 소유자가 아님"
                f" (소유: {owner}). 정당하게 이어받으려면 RL1 재개 절차로 소유를 승계하십시오 — "
                f"`python ~/.codex/hooks/harness_work_state.py resume --root . --work-id {work.get('work_id')} --session <runtime>:<세션UUID>`"
            ),
            "owner": work.get("owner_session_uuid"),
            "work_id": work.get("work_id"),
            "worktree": worktree,
        }
    plan_path = resolve_repo_path(root, work.get("plan_path") if isinstance(work.get("plan_path"), str) else None)
    checklist = get_runtime_checklist(work, plan_path) if plan_path is not None else Checklist(0, 0, 0, None)
    if checklist.remaining <= 0:
        return {"reason": "remaining-0", "message": f"continuation 침묵: plan 에 남은 top-level step 이 없음 ({checklist.completed}/{checklist.total} 완료).", "worktree": worktree}
    if allowed_hard_stop(work, checklist.remaining):
        return {"reason": "honored-stop", "message": f"continuation 침묵: 문서화된 정지 stop_reason={work.get('stop_reason')} 이 유효 (재개는 RL1 절차).", "worktree": worktree}
    return {"reason": "ok", "message": f"정상: continuation 발화 예상 — active work {work.get('work_id')}, 남은 step {checklist.remaining}/{checklist.total}.", "worktree": worktree}


def resume_work(root: Path, work_id: str, token: str) -> tuple[bool, str]:
    """비소유 세션의 소유 승계 — RL1 3단계의 기계화 (HQ1 step-2, 2026-07-21).

    승계 *만* 한다: owner_session_uuid 를 현 세션으로 갱신하고 session_ids 에 추가.
    문서화된 정지(stop_reason 잔존)는 거부한다 — 정지 해소는 재개 프로토콜의 판정
    단계(해소 근거 확인 + ledger 기록)를 먼저 밟아야 하며, 이 커맨드로 우회 불가.
    """
    root = root.resolve()
    state_path = root / STATE_REL
    state = read_json(state_path)
    if not isinstance(state, dict):
        return False, f"거부: {state_path} 없음/손상 — 이 루트에서 approve_harness_plan.py 를 먼저 돌리십시오."
    works = state.get("works")
    work = works.get(work_id) if isinstance(works, dict) else None
    if not isinstance(work, dict):
        return False, f"거부: work {work_id} 없음 (active_work_id={state.get('active_work_id')})."
    status = str(work.get("status") or "")
    if status not in CONTINUABLE_STATUSES:
        return False, f"거부: work {work_id} 상태가 {status or '<없음>'} — 승계는 active/paused 만."
    reason = work.get("stop_reason")
    if isinstance(reason, str) and reason.strip():
        return False, (
            f"거부: work {work_id} 에 문서화된 정지 stop_reason={reason} 가 남아 있음 — "
            "재개 프로토콜의 판정 단계(blocker 해소 근거 확인 + ledger interruption resumed 기록) 후 "
            "stop_reason 해소를 포함한 수동 재개 절차를 따르십시오. 소유 승계로 우회할 수 없습니다."
        )
    work["owner_session_uuid"] = token
    session_ids = work.get("session_ids") if isinstance(work.get("session_ids"), list) else []
    if token not in session_ids:
        session_ids.append(token)
    work["session_ids"] = session_ids
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, f"승계 완료: work {work_id} 소유 = {token}. continuation 이 이 세션에 발화합니다."


def worst_status(statuses: list[str]) -> str:
    order = {"pass": 0, "warn": 1, "fail": 2}
    return max(statuses or ["warn"], key=lambda item: order[item])


def print_text(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        f"harness work state: {summary['status'].upper()} "
        f"({summary['pass']} pass, {summary['warn']} warn, {summary['fail']} fail)"
    )
    active = report.get("active_work")
    if isinstance(active, dict):
        print(f"active: {active.get('work_id')} -> {active.get('plan_path')} ({active.get('status')})")
    checklist = report.get("checklist") or {}
    print(f"checklist: {checklist.get('remaining', 0)}/{checklist.get('total', 0)} remaining")
    if checklist.get("next_task_label"):
        print(f"next: {checklist['next_task_label']}")


def env_session_token(runtime: str = "claude") -> str | None:
    import os

    return normalize_session_token(os.environ.get("CLAUDE_CODE_SESSION_ID"), runtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=("status", "diagnose", "resume", "require-approval", "sync-steps", "next-chained"),
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--session", help="세션 token (기본: CLAUDE_CODE_SESSION_ID 환경변수 → claude:<uuid>)")
    parser.add_argument("--runtime", choices=("claude", "codex"), default="claude")
    parser.add_argument("--work-id", help="resume 대상 work id")
    return parser.parse_args()


def require_approval(root: Path) -> tuple[bool, str]:
    """§E 진입 게이트 (MM7 step-3).

    승인 없이 §E 로 들어가는 것과, milestone 사이의 정상 유휴는 `status` 에서
    둘 다 `PASS 0/0` 으로 보인다 — 구분이 안 되니 "승인을 안 받았다"가 침묵한다
    (HQ1 finding, HQ2 미처리). 이 커맨드는 **진입 시점에만** 물어보는 게이트다:
    승인된 active work 가 없으면 exit 1 + 무엇을 하라는지 안내.
    """
    state = read_json(root / STATE_REL)
    works = state.get("works") if isinstance(state, dict) else None
    active_id = state.get("active_work_id") if isinstance(state, dict) else None
    work = works.get(active_id) if isinstance(works, dict) and isinstance(active_id, str) else None
    if not isinstance(work, dict) or work.get("status") not in CONTINUABLE_STATUSES:
        return False, (
            "거부: 승인된 active work 가 없다 — §E 로 들어갈 수 없다.\n"
            "  계획을 승인 바인딩하라: approve_harness_plan.py <plan> --root . --work-id <id> "
            "--horizon-id <id> --milestone-id <id> --changeset-path <path> --session-id <token>\n"
            "  (milestone 사이의 정상 유휴라면 §E 진입 자체가 이르다)"
        )
    plan_path = resolve_repo_path(root, work.get("plan_path"))
    errors = approval_errors(work, plan_path)
    if errors:
        return False, "거부: 승인 영수증이 성립하지 않는다 — " + "; ".join(errors)
    return True, f"승인 확인: {work.get('work_id')} → {work.get('plan_path')}"


def main() -> int:
    args = parse_args()
    if args.command == "sync-steps":
        state_path = args.root.resolve() / STATE_REL
        state = read_json(state_path)
        if not isinstance(state, dict):
            print(f"거부: {state_path} 없음/손상")
            return 1
        work_id = args.work_id or state.get("active_work_id")
        work = (state.get("works") or {}).get(work_id)
        if not isinstance(work, dict):
            print(f"거부: work {work_id} 없음")
            return 1
        plan = resolve_repo_path(args.root, work.get("plan_path"))
        if plan is None:
            print("거부: plan_path 를 해석할 수 없다")
            return 1
        changed = sync_steps_from_plan(work, plan)
        if changed:
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        done = sum(1 for s in work.get("steps", []) if isinstance(s, dict) and s.get("status") == "completed")
        total = len(work.get("steps") or [])
        print(f"sync-steps: {changed}건 갱신 · {done}/{total} completed")
        return 0
    if args.command == "next-chained":
        # 승인된 계획 연쇄에서 **다음 milestone** 을 묻는다 (2026-07-23 OI3).
        #
        # 왜 커맨드인가: 이 판정은 이미 Stop hook 안에 있었지만, 런타임은 자기가
        # 이어붙인 턴의 Stop 에 `stop_hook_active` 를 실어 보내 훅을 무조건 통과시킨다
        # (무한루프 방지). 그래서 **훅은 milestone 을 최대 한 개만 더 밀어준다** —
        # milestone 5개짜리 연쇄는 중간에 사람이 "계속" 을 말해야 끝난다(2026-07-23 실측).
        # 완료 절차가 이 커맨드를 직접 부르면 연쇄 진행이 훅 발화 횟수와 무관해진다.
        state = read_json(args.root.resolve() / STATE_REL)
        work = active_work(state) if isinstance(state, dict) else None
        chained, unapproved = (
            chained_candidates(args.root.resolve(), work, state)
            if isinstance(work, dict)
            else (None, [])
        )
        if args.json:
            payload = dict(chained) if chained else {}
            if unapproved:
                payload["unapproved_candidates"] = sorted(unapproved)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        elif chained:
            print(f"다음 milestone: {chained['milestone_id']} — {chained['plan_path']}")
            print("  승인 이력 확인됨 — marker 를 active 로 켜고 approve_harness_plan.py 로 등록한 뒤 실행한다.")
        else:
            print("연쇄에 남은 milestone 없음 — 여기서 멈춰도 된다(/harness-done close).")
            if unapproved:
                print(
                    "  미승인 후보 있음(계획서는 있으나 승인 이력 없음): "
                    + ", ".join(sorted(unapproved))
                    + " — 자동 연쇄 대상이 아니다. /harness-plan 승인 게이트로."
                )
        return 0 if chained else 1
    if args.command == "require-approval":
        ok, message = require_approval(args.root)
        print(message)
        return 0 if ok else 1
    if args.command == "resume":
        token = normalize_session_token(args.session, args.runtime) or env_session_token(args.runtime)
        if not args.work_id or token is None:
            print("거부: resume 는 --work-id 와 --session(또는 CLAUDE_CODE_SESSION_ID) 이 필요합니다.")
            return 1
        ok, message = resume_work(args.root, args.work_id, token)
        print(message)
        return 0 if ok else 1
    if args.command == "diagnose":
        token = normalize_session_token(args.session, args.runtime) or env_session_token(args.runtime)
        verdict = diagnose(args.root, token, args.runtime)
        if args.json:
            print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"[{verdict['reason']}] {verdict['message']}")
        return 0 if verdict["reason"] == "ok" else 1
    report = build_status(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if args.strict and report["summary"]["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
