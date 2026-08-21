#!/usr/bin/env python3
"""최종 보고서 → 완료 의식 파생 (HQ3 step-2, 2026-07-21).

완료 경계(harness-done)의 정본 의식 = 최종 보고서(templates/REPORT_TEMPLATE.md, 3섹션 — CF6 다이어트).
이 스크립트가 완성된 보고서를 파싱해 execution ledger 3-event(done_claim →
adversarial_verify → task_completed)를 파생 append 하고 work.json 을 completed 로
전환한다 — 수기 `ledger_append.py close` 의식을 대체한다(구 경로는 하위호환 유지).

파생 강도 보존: 이벤트 생성·검증은 ledger_append 의 builder 를 그대로 재사용한다.
빈 보고서(placeholder 잔존·필수 섹션 공백)는 exit≠0 로 거부 — 보고서 없이/부실하게
완료 의식을 통과할 수 없다.

Usage:
  report_close.py archive/reports/2026-07-21-hq3-....md --task-id HQ3 --root . \
      [--worker <이름>] [--verifier <이름>] [--summary "<사용자용 한 문장>"]

보고서 §3(증거) 파싱 계약: `실표면:` 줄(surface smoke — 없으면 'none — <이유>')
과 `재현:` 줄(독립 재실행 커맨드)이 필수다. 템플릿이 이 두 줄을 안내한다.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--worker", default=None)
    parser.add_argument("--verifier", default=None)
    parser.add_argument("--summary", default=None)
    args = parser.parse_args(argv)

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
    if not is_unfilled(extract_line(evidence_body, HARVEST_PREFIX)):
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

    task_id = args.task_id
    worker = args.worker or f"report-author:{task_id}"
    verifier = args.verifier or f"report-verifier:{task_id}"
    rel_report = str(report_path.relative_to(root)) if report_path.is_relative_to(root) else str(report_path)
    changesets = sorted(set(re.findall(r"changesets/[0-9]{8}-[\w-]+", text))) or [rel_report]
    tests = [ln.strip().lstrip("-*").strip() for ln in evidence_body.splitlines() if re.search(r"pytest|PASS|test|검증|smoke", ln, re.I)][:5]
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


if __name__ == "__main__":
    raise SystemExit(main())
