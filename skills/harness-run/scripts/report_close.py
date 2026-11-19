#!/usr/bin/env python3
"""최종 보고서 → 완료 의식 파생 (HQ3 step-2, 2026-07-21).

완료 경계(harness-done)의 정본 의식 = 최종 보고서(harness-done 스킬의 templates/REPORT_TEMPLATE.md, 3섹션 — CF6 다이어트).
이 스크립트가 완성된 보고서를 파싱해 execution ledger 3-event(done_claim →
adversarial_verify → task_completed)를 파생 append 하고 work.json 을 completed 로
전환한다 — 수기 `ledger_append.py close` 의식을 대체한다(구 경로는 하위호환 유지).

파생 강도 보존: 이벤트 생성·검증은 ledger_append 의 builder 를 그대로 재사용한다.
빈 보고서(placeholder 잔존·필수 섹션 공백)는 exit≠0 로 거부 — 보고서 없이/부실하게
완료 의식을 통과할 수 없다.

Usage:
  report_close.py archive/reports/2026-07-21-hq3-....md --task-id HQ3 --root . \
      [--worker <이름>] [--verifier <이름>] [--summary "<사용자용 한 문장>"]

보고서 §3(증거) 파싱 계약: `실표면:` 줄(surface smoke — 없으면 'none — <이유>'),
`재현:` 줄(독립 재실행 커맨드), `감사:` 줄(마감 감사 결과 — 안 돌았으면 'none — <사유>',
ADR 0015 §6)이 필수다. 템플릿이 이 세 줄을 안내한다.

§3 자동 증거 블록(2026-11-16): git 레포면 `harness-done/bin/report_evidence.py` 가 쓴 표식 블록이 있어야 하고
그 `기준 HEAD` 가 현재 HEAD 여야 한다 — 손으로 옮겨 적은 커밋·수치가 낡는 것을 막는다.
스위트 대조(2026-11-06): git 레포면 `.harness/suite-gate.json`(harness-done/bin/suite_gate.py 가
쓴다)이 현재 HEAD 의 pass·none·waived 여야 닫힌다. waived 면 §3 `스위트:` 줄도 필수다.
"""

from __future__ import annotations

import argparse
import subprocess
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger_append  # noqa: E402

# CF6 step-3 (2026-07-22): 7섹션 → 3섹션.
# 구 7섹션 중 파생에 실제로 쓰이던 것은 결과(summary fallback)·이슈(risks)·증거(전부)
# 뿐이고, 나머지 4개(문제 정의·Objective 연결·경로·후속 제안)는 "비어 있지 않은지" 만
# 검사받는 순수 작문이었다. 사용자가 완료 보고서를 평소 다시 읽지 않으며 용도는 사고 시
# 회고임이 확인돼(2026-07-22), 사고 회고에 필요한 것만 남겼다.
SECTION_TITLES = ["결과", "이슈와 해결", "증거"]

# 구 제목으로 쓰인 보고서(2026-07-21 이전)도 계속 파싱되게 한다 — 기록은 동결이 원칙이라
# 과거 문서를 고쳐 쓰지 않는다.
SECTION_ALIASES = {
    "구현 결과": "결과",
    "결과물과 증거": "증거",
}


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def split_sections(text: str) -> dict[str, str]:
    """`## N. 제목` 헤딩으로 본문을 가른다. 제목 매칭은 접두 일치(뒤 괄호 허용)."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+\d\.\s*(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            title = m.group(1)
            alias = next((v for k, v in SECTION_ALIASES.items() if title.startswith(k)), None)
            current = alias or next((t for t in SECTION_TITLES if title.startswith(t)), title)
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def section_errors(sections: dict[str, str]) -> list[str]:
    errors = []
    for title in SECTION_TITLES:
        body = sections.get(title, "")
        stripped = re.sub(r"\{[^}]*\}", "", body).strip()  # 템플릿 placeholder 제거 후 판정
        if not stripped:
            errors.append(f"섹션 '{title}' 이 비어 있거나 템플릿 placeholder 그대로다")
    return errors


# 불릿·강조 표기를 벗긴다. `- 수확:` `**수확**:` `- **수확**:` 는 같은 줄이다 —
# 게이트가 서식을 감시하면 선언을 해 놓고도 거절당한다(2026-08-20 M6 실측 재현).
_LINE_MARKERS = "-*_ \t"


def strip_markers(line: str) -> str:
    return line.strip().lstrip(_LINE_MARKERS).strip()


# 값 쪽은 **닫는 강조 + 콜론 하나**만 벗긴다. 마커 집합으로 lstrip 하면 값 자신의 머리글자를
# 먹는다 — `재현: --pre-approval 로 재실행` 이 `pre-approval 로 재실행` 이 되어 동결 원장에
# 틀린 재현 커맨드가 들어간다(2026-08-20 M6 코드 리뷰 실측).
# 콜론을 **요구**하는 것이 두 번째 몫이다: 그러지 않으면 `- 재현 불가한 …` 같은 산문 줄이
# `재현:` 필드로 읽혀 진짜 줄을 가리고, `수확:` 예외가 OI3 게이트의 우회로가 된다.
_VALUE_RE = re.compile(r"^[*_\s]*:\s*(.*)$")


def extract_line(body: str, prefix: str) -> str:
    for line in body.splitlines():
        text = strip_markers(line)
        if not text.startswith(prefix):
            continue
        match = _VALUE_RE.match(text[len(prefix):])
        if match is None:
            continue  # 콜론이 없으면 그 필드 줄이 아니다
        return match.group(1).strip()
    return ""


def is_unfilled(value: str) -> str:
    """템플릿 placeholder 만 남은 값이면 빈 문자열. 채워졌으면 값 그대로.

    구 게이트는 줄이 **존재하기만** 하면 통과시켜서, 템플릿의 `{…}` 를 그대로 둔 보고서가
    조용히 닫혔다(2026-08-20 M6 코드 리뷰 실측: `- 수확: {이 milestone 에서 …}` rc 0).
    판정을 안 한 것이 판정으로 기록되는 것 — M6 이 없애려던 실패 모드 그 자체다.
    `section_errors` 가 이미 같은 정규화를 쓴다.
    """
    return value if re.sub(r"\{[^}]*\}", "", value).strip() else ""


def first_sentence(body: str) -> str:
    text = " ".join(body.split())
    m = re.match(r"(.+?[.!?다])\s", text + " ")
    return (m.group(1) if m else text)[:200]



# (제거 2026-07-23, 재조립 P3) 분량 대조 `declared_minimum`/`measured_changesets`/
# `reconcile_line` — **horizon 레벨 산출물**이었고 horizon 층 자체가 폐지됐다(C4·C9).
# 선언 `예상 분량: ~N changeset` 을 두던 자리(horizon 설계서)가 사라졌으므로 대조할
# 선언이 없다. 크기 캘리브레이션은 계획서의 step 수로 되돌아간다.


NL = chr(10)


# ── 평가 못 한 검사는 통과가 아니다 (2026-07-23 OI3 step-3) ──────────────────
#
# dryforge `go/SKILL.md:334-341`: *"An unevaluable check is a fail, not a pass."*
# 검사가 green 인 것은 **assertion 자체가 평가돼 성공을 보고했을 때**뿐이다. 명령이
# assertion 전에 죽었거나, 서버가 안 떴거나, 매칭 출력이 비었으면 그건 실패다.
# **부작용에서 통과를 추론하지 않는다** — "파일이 생겼다"·"에러가 안 났다"는 증거가 아니다.
#
# 우리 완료 판정 표면은 이 스크립트다. 여기서 하는 일은 하나 — 보고서에 "평가 못 했다"는
# 신호가 있는데 그게 **한 줄로 표면화되지 않았으면 완료를 거절한다.** 판정은 사람이 하고,
# 이 게이트는 *조용히 통과하는 것*만 막는다.
UNEVALUABLE_SIGNALS = (
    "평가 못", "평가 불가", "측정 불가", "측정할 수 없", "확인 못", "확인 불가",
    "재현 불가", "돌려보지 못", "실행 못", "unevaluable", "could not verify",
)
UNEVALUABLE_DECLARATION = "평가 못 함:"


# `실표면:` 이 **부작용으로 통과를 주장**하는 형태. assertion 이 돈 게 아니라 흔적을 본 것이다.
SIDE_EFFECT_CLAIMS = (
    "에러가 안", "에러 없이", "오류 없이", "파일이 생겼", "로그에 찍", "로그가 남",
    "no error", "looks fine", "문제 없어 보",
)


# **만든 것과 검증한 것은 다르다** (2026-07-23 DC4). OI3 이 막은 것은 *검사가 못 돈* 경우
# (평가 못 함)이고, 여기서 막는 것은 **검사를 애초에 안 만든** 경우다 — dryforge
# `harness-format.md:279-285`: *"code that is implemented but has no tests is 'built,
# untested' (state it that way; the coverage gap is itself signal)."*
#
# 막지 않고 **말하게** 한다. 막으면 우회 문구가 생긴다("검증: 완료") — 그건 지금보다 나쁘다.
# `검증:` 줄에 실행 근거(커맨드·통과 수치·게이트 이름)가 하나도 없으면, 그건 검증이 아니라
# 주장이므로 `구현됨·미검증:` 선언을 요구한다.
UNVERIFIED_DECLARATION = "구현됨·미검증:"

# ── kg 수확 후보를 검사 가능한 대상으로 (2026-08-20 M6 step-1) ────────────────
# 구 계약에서 kg 인입은 `harness-done/SKILL.md` 의 번호 밖 불릿에 "non-blocking" 으로만
# 있었다. 그래서 빠뜨려도 **아무도 모른 채 보고서가 정상으로 닫혔다**(M5 실측, n=1).
# 규율을 늘리는 게 아니라 누락을 관측 가능하게 만든다 — `없음` 은 그대로 통과시킨다.
HARVEST_PREFIX = "수확"
HARVEST_HELP = (
    "§3 증거에 `수확:` 줄이 필요하다 — 이 milestone 에서 kg(지식 그래프)로 올릴 후보를 적는다.\n"
    "  형식: `- 수확: <노드 후보 이름> — <출처 한 줄(재현 명령·커밋·URL)>` (여러 건이면 ` / ` 로 나열, 최대 2건)\n"
    "  후보가 없으면 `- 수확: 없음` 또는 `- 수확: 없음 — <이유>` 로 적는다. 후보 0건이 정상 기본값이다."
)
_RUN_EVIDENCE_RE = re.compile(
    r"`[^`]+`|\bpytest\b|\bPASS\b|\bFAIL\b|passed|exit\s*(?:code)?\s*\d|doctor|smoke|\d+\s*(?:건|개|passed)",
    re.I,
)


def unverified_error(evidence_body: str) -> str:
    """`검증:` 줄이 실행 근거 없는 주장이면 거부 사유. 없으면 빈 문자열."""
    plain = evidence_body.replace("*", "").replace("_", "")
    if UNVERIFIED_DECLARATION in plain:
        return ""
    line = extract_line(evidence_body, "검증")
    if not line:
        return ""  # `검증:` 줄 자체의 필수 여부는 템플릿·section_errors 소관
    if _RUN_EVIDENCE_RE.search(line):
        return ""
    return (
        f"`검증:` 줄에 실행 근거가 없다: {line[:90]}\n"
        "  만든 것과 검증한 것은 다르다 — 돌린 커맨드·게이트 이름·통과 수치 중 하나를 적거나,\n"
        f"  테스트를 안 만들었으면 `{UNVERIFIED_DECLARATION} <무엇이 미검증인가>` 로 그렇게 적는다.\n"
        "  (커버리지 공백은 감출 것이 아니라 그 자체가 신호다)"
    )


def unevaluable_error(evidence_body: str, surface_smoke: str) -> str:
    """평가 못 한 항목이 **표면화 없이** 섞여 있으면 거부 사유. 없으면 빈 문자열."""
    smoke = (surface_smoke or "").strip()
    if smoke and not smoke.lower().startswith("none") and any(
        claim in smoke for claim in SIDE_EFFECT_CLAIMS
    ):
        return (
            f"`실표면:` 이 부작용으로 통과를 주장한다: {smoke[:90]}\n"
            "  assertion 이 실제로 평가돼 성공을 보고했을 때만 통과다 — 무엇을 두드려 "
            "무엇이 관측됐는지(exit code·응답·출력)를 적거나 `none — <이유>` 로 적는다."
        )
    # 마크다운 강조를 벗기고 본다. 첫 실사용에서 `- **평가 못 함**: …` 로 적었다가 걸렸다
    # (2026-07-23) — 선언을 해 놓고도 별표 때문에 거절되면 게이트가 서식을 감시하는 셈이다.
    if UNEVALUABLE_DECLARATION in evidence_body.replace("*", "").replace("_", ""):
        return ""
    hits = []
    for line in evidence_body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|--"):
            continue
        if strip_markers(stripped).startswith(HARVEST_PREFIX + ":"):
            continue  # `수확:` 은 검사 결과 서술이 아니라 분류 판정이다 (M6 D1/B2)
        if strip_markers(stripped).startswith(("감사:", "리뷰:")):
            # 다른 자리(감사자·리뷰어)의 처분 줄이다. `감사: none — …` 에 스폰 조건 이름(「평가 못 함」)을
            # 적었다가 거부되는 함정이 SKILL 경고문으로만 막혀 있었다(2026-09-22 실측 → 2026-11-16 코드로).
            continue
        if any(signal in stripped for signal in UNEVALUABLE_SIGNALS):
            hits.append(stripped[:90])
    if not hits:
        return ""
    shown = " / ".join(hits[:3])
    return (
        "§3 증거에 **평가하지 못한 검사**로 읽히는 줄이 있는데 표면화되지 않았다: "
        + shown + "\n"
        f"  평가 못 한 검사는 통과가 아니다 — `{UNEVALUABLE_DECLARATION} <무엇을 왜 못 쟀나>` "
        "줄을 §3 에 추가해 명시하거나, 검사를 고쳐 실제로 통과시킨 뒤 다시 닫는다.\n"
        "  (부작용에서 통과를 추론하지 않는다 — 파일이 생겼다·에러가 안 났다는 증거가 아니다)"
    )


def durability_error(root: Path, report_path: Path) -> str | None:
    """완료 노트가 git 에 남는지 검사. 남지 않으면 사유 문자열, 정상이면 None.

    배치 규약은 완료 노트를 `archive/reports/` 에 두는데, 일부 레포는 `archive/` 를
    폐기물 창고로 쓰며 통째로 gitignore 한다. 그러면 close 는 성공하는데 보고서는
    로컬에만 남고 ROADMAP 의 `evidence=` 링크가 원격에서 깨진다(2026-07-23 실측).
    완료 = 증거가 남는 것이므로, 남지 않으면 닫지 않는다.
    """
    try:
        rel = report_path.relative_to(root)
    except ValueError:
        return None  # 레포 밖 경로는 이 계약의 대상이 아니다
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                cwd=root, capture_output=True, text=True, timeout=15)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None  # git 레포가 아니면 내구성 계약 미적용
        out = subprocess.run(["git", "check-ignore", "-q", str(rel)],
                             cwd=root, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None  # git 을 못 부르면 막지 않는다(게이트가 작업을 볼모로 잡지 않음)
    # 2026-08-06 감사 #12: `check-ignore` 는 "무시 안 됨"에 1, **오류에 128** 을 돌려준다.
    # 구 코드는 `!= 0` 을 전부 "정상"으로 읽어 **오류를 검사 통과로 바꿨다.** 막지는 않는다
    # (이 게이트는 git 문제로 작업을 볼모 잡지 않는 게 설계다) — 대신 침묵을 없앤다.
    if out.returncode == 1:
        return None  # ignore 되지 않음 = 정상
    if out.returncode != 0:
        print(f"warning: git check-ignore 가 오류로 끝났다(rc={out.returncode}) — "
              f"완료 노트의 추적 여부를 확인하지 못했다: {rel}", file=sys.stderr)
        return None
    return NL.join([
        "완료 노트가 gitignore 로 추적 불가: " + str(rel),
        "  → 완료는 증거가 레포에 남는 것을 뜻한다. 지금 닫으면 보고서는 이 기기에만 남고",
        "    ROADMAP 의 evidence= 링크가 원격에서 깨진다.",
        "  → 조치: .gitignore 에 예외를 추가한다 (archive/ 를 무시하는 레포면 !archive/reports/),",
        "    또는 harness scripts/fix_report_durability.py --root . 로 일괄 교정.",
    ])


def suite_gate_check(root: Path, evidence_body: str) -> tuple[str | None, str | None]:
    """(거부 사유, 통과 요약). 마감 직전 스위트 실행 기록을 현재 HEAD 와 대조한다(2026-11-06).

    git 레포가 아니면 대조할 HEAD 가 없어 경고만 하고 넘긴다 — durability_error 와 같은 이유로
    git 문제로 작업을 볼모 잡지 않는다.
    """
    command = f'python "{Path(__file__).resolve().parents[2] / "harness-done" / "bin" / "suite_gate.py"}" --root "{root}"'
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is None or out.returncode != 0:
        print(f"warning: HEAD 를 읽지 못해 스위트 기록을 대조하지 않았다: {root}", file=sys.stderr)
        return None, None
    head = out.stdout.strip()

    try:
        record = json.loads((root / ".harness" / "suite-gate.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"스위트 실행 기록이 없다 — 닫기 전에 돌린다: {command}", None
    status = record.get("status")
    # 덮음 판정은 suite_gate.record_scope 한 곳에만 둔다(M28 D10) — 같은 커밋이거나 기록 파일만 바뀐 커밋이면 덮인다
    sys.path.insert(0, str(EVIDENCE_TOOL.parent))
    try:
        import suite_gate
    finally:
        sys.path.pop(0)
    covered, why = suite_gate.record_scope(root, record=record)
    if not covered:
        return f"스위트 기록이 다른 커밋의 것이다({str(record.get('head'))[:9]} ≠ {head[:9]}, {why}) — 다시 돌린다: {command}", None
    note = "" if why == "같은 커밋" else f" — {why}"
    if status == "waived":
        if not is_unfilled(extract_line(evidence_body, "스위트")):
            return f"스위트를 면제했으면 §3 에 `스위트: waived — <사유>` 줄이 필요하다 (기록된 사유: {record.get('reason')})", None
        return None, f"스위트 면제: {record.get('reason')}{note}"
    if status == "none":
        return None, f"스위트 없음: {record.get('reason')}{note}"
    if status == "pass":
        return None, f"스위트 통과: {record.get('command')} (dirty {record.get('dirty')}){note}"
    return f"스위트가 실패 상태다({record.get('command')}, exit {record.get('exit_code')}) — 고치고 다시 돌린다: {command}", None


EVIDENCE_TOOL = Path(__file__).resolve().parents[2] / "harness-done" / "bin" / "report_evidence.py"


def evidence_block_error(root: Path, text: str) -> str | None:
    """§3 자동 증거 블록이 현재 HEAD 기준인지 본다(2026-11-16).

    커밋 범위·HEAD·트리·스위트·산출물 추적 줄은 `report_evidence.py` 가 쓴다 — 손으로 옮겨 적은
    수치·낡은 커밋 기준 증거가 30일 감사 막는 지적의 큰 몫이었다. git 레포가 아니면 대조할 HEAD 가
    없어 넘긴다(suite_gate_check 와 같은 이유).
    """
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    head = out.stdout.strip()
    command = f'python "{EVIDENCE_TOOL}" --root "{root}" --base <milestone 시작 직전 커밋> --plan <계획서> --changeset <경로> --write <노트>'
    sys.path.insert(0, str(EVIDENCE_TOOL.parent))
    try:
        import report_evidence
    finally:
        sys.path.pop(0)
    block = report_evidence.block_head(text)
    if block is None:
        return f"§3 자동 증거 블록이 없다 — 생성한다: {command}"
    if not head.startswith(block):
        return f"§3 자동 증거 블록이 다른 커밋 기준이다({block} ≠ {head[:9]}) — 다시 생성한다: {command}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--worker", default=None)
    parser.add_argument("--verifier", default=None)
    parser.add_argument("--summary", default=None)
    # M24 (2026-11-03): 외부 결과로 접는 milestone — 중단 노트(중단 사유·동결 산출물·재개 조건)
    # 를 검사해 `task_dropped` 한 건만 남긴다. 완료 3-event 를 파생하지 않는다.
    parser.add_argument("--drop", action="store_true", help="중단(dropped) 종결 — 중단 노트로 닫는다")
    parser.add_argument("--milestone-id", default=None,
                        help="--drop 에서 기록할 milestone id (기본 = --task-id)")
    args = parser.parse_args(argv)
    if args.drop:
        return close_dropped(args)

    root = args.root.resolve()
    report_path = args.report if args.report.is_absolute() else root / args.report
    try:
        text = report_path.read_text(encoding="utf-8-sig")
    except OSError as error:
        return fail(f"보고서를 읽을 수 없음: {report_path} ({error})")

    sections = split_sections(text)
    errors = section_errors(sections)
    if errors:
        return fail("빈 보고서 거부 — " + "; ".join(errors))

    evidence_body = sections["증거"]
    surface_smoke = is_unfilled(extract_line(evidence_body, "실표면"))
    repro = is_unfilled(extract_line(evidence_body, "재현"))
    if not surface_smoke:
        return fail("§3 증거에 `실표면:` 줄이 필요하다 — 실표면 스모크 결과 1줄 또는 'none — <이유>' (IMP-013)")
    if not repro:
        return fail("§3 증거에 `재현:` 줄이 필요하다 — 독립 재실행 커맨드/방법 1줄")
    # 2026-09-22 ADR 0015 §6: 마감 감사 자리를 세우면서 `감사:` 를 `실표면:`·`재현:` 과 같은
    # 강도로 올렸다. 감사가 안 돈 마감도 **왜 안 돌았는지**를 적어야 닫힌다 — 생략이 조용히
    # 일어나는 것이 이 줄을 만든 이유다(`리뷰:` 는 현행 비강제 유지).
    audit = is_unfilled(extract_line(evidence_body, "감사"))
    if not audit:
        return fail(
            "§3 증거에 `감사:` 줄이 필요하다 — 마감 감사자 지적 n건과 처분, "
            "또는 'none — <조건 미해당 사유>' (ADR 0015 §6)"
        )
    # 2026-09-21 사용자 결정(절차 다이어트): `수확:` 은 **선택**이다 — 후보 0건이 기본값인 줄을
    # 의무로 두면 `없음` 만 찍히는 의식이 된다. 있으면 형식대로 적고, 없으면 줄 자체를 생략한다.
    # 줄이 **있는데** 템플릿 표식 그대로면 판정을 안 한 것이라 여전히 거부한다.
    harvest_line = extract_line(evidence_body, HARVEST_PREFIX)
    if harvest_line and not is_unfilled(harvest_line):
        return fail(HARVEST_HELP)

    unevaluable = unevaluable_error(evidence_body, surface_smoke)
    if unevaluable:
        return fail(unevaluable)

    unverified = unverified_error(evidence_body)
    if unverified:
        return fail(unverified)

    durability = durability_error(root, report_path)
    if durability:
        return fail(durability)

    suite_error, suite_summary = suite_gate_check(root, evidence_body)
    if suite_error:
        return fail(suite_error)

    block_error = evidence_block_error(root, text)
    if block_error:
        return fail(block_error)

    task_id = args.task_id
    worker = args.worker or f"report-author:{task_id}"
    verifier = args.verifier or f"report-verifier:{task_id}"
    rel_report = str(report_path.relative_to(root)) if report_path.is_relative_to(root) else str(report_path)
    changesets = sorted(set(re.findall(r"changesets/[0-9]{8}-[\w-]+", text))) or [rel_report]
    tests = [ln.strip().lstrip("-*").strip() for ln in evidence_body.splitlines() if re.search(r"pytest|PASS|test|검증|smoke", ln, re.I)][:5]
    if suite_summary:
        tests.insert(0, suite_summary)
    issues = sections["이슈와 해결"]

    ledger = root / ".harness" / "execution-ledger.jsonl"
    prior = ledger_append.load_records(ledger)

    ns = argparse.Namespace(
        task_id=task_id, worker=worker,
        changed_files=changesets, tests=tests or [first_sentence(evidence_body)],
        evidence=[rel_report], cleanup=[extract_line(evidence_body, "정리") or "보고서 참조 — 별도 잔여 자원 없음"],
        risks=[first_sentence(issues) if issues.strip() not in {"없음", "없음."} else "none known"],
        verifier=verifier, verdict="confirmed", repro=repro, surface_smoke=surface_smoke,
        spec_verdict=None, quality_verdict=None, near_misses=[], residual_risk=None,
    )
    records = []
    for build in (ledger_append.build_done_claim,
                  lambda a: ledger_append.build_verify(a, prior + records),
                  lambda a: ledger_append.build_complete(a, prior + records)):
        rec = build(ns)
        if isinstance(rec, str):
            return fail(rec)
        records.append(rec)

    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary = args.summary or first_sentence(sections["결과"])
    ledger_append.stage_completion_summary(ledger, task_id, summary)
    # work.json completed 전환 (harness-done — active_work_id 는 비우지 않는다: Stop 훅 완료 알림이 읽음)
    work_path = root / ".harness" / "work.json"
    try:
        state = json.loads(work_path.read_text(encoding="utf-8"))
        work = ledger_append._find_work_for_task(state, task_id)
        if isinstance(work, dict):
            work["status"] = "completed"
            work_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

    print(f"report_close: {rel_report} → 3-event 파생 append + work {task_id} completed")
    return 0


DROP_SECTION_TITLES = ["중단 사유", "동결 산출물", "재개 조건"]


def close_dropped(args: argparse.Namespace) -> int:
    """중단 노트 → ledger `task_dropped` 1건 + work status `dropped` (work 가 있을 때만).

    계획서·work 없이 ROADMAP 에만 있던 milestone 도 닫을 수 있어야 한다 — 그래서 work 가
    없으면 거부하지 않고 ledger 기록만 남긴다(next-connect 2026-11-02 마찰).
    """
    root = args.root.resolve()
    report_path = args.report if args.report.is_absolute() else root / args.report
    try:
        text = report_path.read_text(encoding="utf-8-sig")
    except OSError as error:
        return fail(f"중단 노트를 읽을 수 없음: {report_path} ({error})")
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+\d\.\s*(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            title = m.group(1)
            current = next((t for t in DROP_SECTION_TITLES if title.startswith(t)), title)
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    errors = []
    for title in DROP_SECTION_TITLES:
        body = re.sub(r"\{[^}]*\}", "", sections.get(title, "")).strip()
        if not body:
            errors.append(f"섹션 '{title}' 이 비어 있거나 템플릿 placeholder 그대로다")
    if errors:
        return fail("빈 중단 노트 거부 — " + "; ".join(errors))
    basis = is_unfilled(extract_line(sections["중단 사유"], "근거"))
    if not basis:
        return fail("§1 중단 사유에 `근거:` 줄이 필요하다 — 접게 만든 외부 결과의 출처(메일·공지·URL·날짜)")
    # 감사 지적 1 (2026-11-03): `근거:` 한 줄만 있어도 절이 비지 않은 것으로 보였다 —
    # 사유 문장 자체가 채워졌는지 따로 본다.
    reason_body = "\n".join(
        ln for ln in sections["중단 사유"].splitlines() if not strip_markers(ln).startswith("근거")
    )
    if not re.sub(r"\{[^}]*\}", "", reason_body).strip():
        return fail("§1 중단 사유의 사유 문장이 비어 있거나 템플릿 placeholder 그대로다 — `근거:` 줄만으로는 닫지 않는다")
    durability = durability_error(root, report_path)
    if durability:
        return fail(durability)

    task_id = args.task_id
    milestone_id = args.milestone_id or task_id
    rel_report = str(report_path.relative_to(root)) if report_path.is_relative_to(root) else str(report_path)
    reason = args.summary or first_sentence(reason_body)
    ledger = root / ".harness" / "execution-ledger.jsonl"
    prior = ledger_append.load_records(ledger) if ledger.is_file() else []
    # 감사 지적 2: 이미 완료된 것을 중단으로 덮으면 ROADMAP·work·ledger 가 반쪽만 바뀐다 —
    # 무엇이든 쓰기 전에 거부한다.
    work_path = root / ".harness" / "work.json"
    state = None
    if work_path.is_file():
        try:
            state = json.loads(work_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = None
    work = ledger_append._find_work_for_task(state, task_id) if isinstance(state, dict) else None
    if isinstance(work, dict) and work.get("status") in {"completed", "abandoned"}:
        return fail(f"work {task_id} 는 이미 {work.get('status')} 다 — 중단으로 덮지 않는다")
    if any(r.get("event") == "task_completed" and r.get("task_id") == task_id for r in prior):
        return fail(f"ledger 에 {task_id} 의 task_completed 가 이미 있다 — 중단으로 덮지 않는다")
    roadmap = root / "ROADMAP.md"
    if roadmap.is_file():
        marker = re.search(
            r'<!--\s*harness:milestone\s+[^>]*id="' + re.escape(milestone_id) + r'"[^>]*status="completed"',
            roadmap.read_text(encoding="utf-8", errors="replace"),
        )
        if marker:
            return fail(f"ROADMAP 의 {milestone_id} 는 이미 completed 다 — 중단으로 덮지 않는다")
    if any(r.get("event") == "task_dropped" and r.get("task_id") == task_id for r in prior):
        print(f"report_close --drop: {task_id} 는 이미 task_dropped 기록이 있다 — 변화 없음")
        return 0
    record = ledger_append.build_dropped(task_id, milestone_id, [rel_report], reason, basis)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    work_note = "work 없음 — ledger 기록만"
    if isinstance(work, dict):
        work["status"] = "dropped"
        work["drop_reason"] = reason
        work_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        work_note = f"work {task_id} dropped"
    print(f"report_close --drop: {rel_report} → task_dropped append ({milestone_id}) + {work_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
