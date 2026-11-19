#!/usr/bin/env python3
"""완료 노트 §3 의 기계 사실 줄을 HEAD 기준으로 생성한다 (2026-11-16).

30일 마감 감사의 막는 지적 225건 중 141건이 노트를 손으로 쓰다 생긴 오류였다(수치 불일치·
낡은 커밋 기준 증거·마감 기록 누락 — custom-skills `changesets/20261113-audit-third-batch.md`).
커밋 범위·HEAD·커밋 수·트리 상태·스위트 기록·changeset·산출물 추적 여부는 기계가 아는 값이라
모델이 옮겨 적지 않고 이 스크립트가 쓴다. 판단 줄(실표면·재현·리뷰·감사·구현됨·미검증)은
모델이 쓴다.

블록은 표식 사이에 산다. `--write` 는 표식이 있으면 그 사이를 갈아끼우고, 없으면 `## 3. 증거`
제목 바로 아래에 넣는다. 커밋이 더 생기면 다시 돌린다 — `report_close.py` 가 블록의 HEAD 를
현재 HEAD 와 대조해 어긋나면 거부한다.

Usage:
  report_evidence.py --root <레포> --base <milestone 시작 직전 커밋> [--plan <계획서>]
                     [--changeset <경로> ...] [--write <완료 노트>]

exit: 0 = 문제 없음 / 1 = 블록에 경고가 있음(미커밋·스위트 미통과·추적 안 된 산출물) / 2 = 사용법·git 오류
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 같은 폴더의 suite_gate — 스크립트 실행·테스트·report_close 어느 경로로 불려도 한 번만 가져온다
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import suite_gate  # noqa: E402
finally:
    sys.path.pop(0)

START = "<!-- 자동 증거 시작: report_evidence.py 가 쓴다 — 손으로 고치지 말고 다시 돌린다 -->"
END = "<!-- 자동 증거 끝 -->"
HEAD_LINE = re.compile(r"^- 기준 HEAD: `([0-9a-f]{7,40})`", re.M)
EVIDENCE_HEADING = re.compile(r"^##\s*3\.?\s*증거.*$", re.M)
DONE_STEP = re.compile(r"^\s*-\s*\[[xX]\]\s*\*\*(step-[\w.-]+)")
FILES_FIELD = re.compile(r"^\s*-\s*Files\s*:\s*(.+)$")


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def tracked(root: Path, rel: str) -> bool:
    return bool((git(root, "ls-files", "--", rel) or "").strip())


def ignored(root: Path, rel: str) -> bool:
    """`git check-ignore` 가 gitignore 대상이라고 판정하면 True (추적 중인 파일은 대상이 아니다)."""
    try:
        out = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", rel],
                             capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def harness_state(path: str) -> bool:
    """하네스가 스스로 쓰는 상태 경로(`.harness/` 아래 전부). suite_gate 가 증거 생성보다 먼저 돌아
    이 경로의 미커밋은 구조적으로 사라질 수 없어 미커밋 경고에서 뺀다."""
    return path == ".harness" or path.startswith(".harness/")


def suite_line(root: Path, head: str) -> tuple[str, bool]:
    try:
        rec = json.loads((root / ".harness" / "suite-gate.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "기록 없음 — `suite_gate.py` 를 먼저 돌린다", False
    status, rec_head = rec.get("status"), str(rec.get("head") or "")
    # 덮음 판정은 suite_gate.record_scope 한 곳에만 둔다(M28 D10) — 같은 커밋이거나 기록 파일만 바뀐 커밋이면 덮인다
    covered, why = suite_gate.record_scope(root, head, record=rec)
    if not covered:
        return f"다른 커밋의 기록({rec_head[:9]}, {why}) — 다시 돌린다", False
    note = "" if why == "같은 커밋" else f"; {why}"
    elapsed = rec.get("elapsed_seconds")
    took = f", {elapsed:.0f}초" if isinstance(elapsed, (int, float)) else ""
    if status == "pass":
        return f"통과 — `{rec.get('command')}` (HEAD {head[:9]}{took}{note})", True
    if status == "none":
        return f"없음 — {rec.get('reason')}{note}", True
    if status == "waived":
        return f"waived — {rec.get('reason')}{note}", True
    if status == "running":
        return "실행 중이거나 중단된 기록 — 스위트가 끝난 뒤 다시 생성한다", False
    return f"실패 — `{rec.get('command')}` exit {rec.get('exit_code')}", False


def plan_files(plan: Path) -> tuple[int, list[str]]:
    """완료(`[x]`) step 의 `Files:` 에서 경로처럼 생긴 토큰을 뽑는다."""
    steps, paths, in_done = 0, [], False
    for line in plan.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*-\s*\[[ xX]\]\s*\*\*step-", line):
            in_done = bool(DONE_STEP.match(line))
            steps += in_done
            continue
        m = FILES_FIELD.match(line)
        if not (in_done and m):
            continue
        field = m.group(1)
        tokens = re.findall(r"`([^`]+)`", field) or re.split(r"[,·;]\s*", field)
        for tok in tokens:
            tok = re.sub(r"\s*\(.*?\)\s*$", "", tok.strip()).split("::")[0].strip()
            if tok and " " not in tok and not any(c in tok for c in "*?{}<>") and ("/" in tok or "." in tok):
                paths.append(tok.lstrip("./") if tok.startswith("./") else tok)
    return steps, list(dict.fromkeys(paths))


def build(root: Path, base: str, plan: Path | None, changesets: list[str], report: Path | None) -> tuple[str, list[str]]:
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    if not head:
        raise SystemExit(f"report_evidence: HEAD 를 읽지 못했다: {root}")
    base_full = (git(root, "rev-parse", "--verify", f"{base}^{{commit}}") or "").strip()
    if not base_full:
        raise SystemExit(f"report_evidence: 기준 커밋을 찾지 못했다: {base}")
    warnings: list[str] = []
    count = (git(root, "rev-list", "--count", f"{base_full}..{head}") or "?").strip()
    lines = [f"- 기준 HEAD: `{head[:9]}` · 범위 `{base_full[:9]}..{head[:9]}` · 커밋 {count}개"]

    report_rel = None
    if report is not None:
        try:
            report_rel = report.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            report_rel = None
    dirty = []
    # --untracked-files=all: 추적 안 된 새 폴더를 `archive/` 로 접지 않고 파일 단위로 받아야 노트 자신을 뺄 수 있다
    for ln in (git(root, "status", "--porcelain", "--untracked-files=all") or "").splitlines():
        path = ln[3:].strip().strip('"')
        if path and path != report_rel and not harness_state(path):
            dirty.append(path)
    if dirty:
        shown = ", ".join(f"`{p}`" for p in dirty[:3]) + (f" 외 {len(dirty) - 3}개" if len(dirty) > 3 else "")
        lines.append(f"- 트리: 미커밋 {len(dirty)}개 ({shown}) — 커밋하고 다시 돌린다")
        warnings.append("미커밋 변경")
    else:
        lines.append("- 트리: 깨끗 (노트 파일 제외)")

    text, ok = suite_line(root, head)
    lines.append(f"- 스위트 기록: {text}")
    if not ok:
        warnings.append("스위트")

    for cs in changesets:
        state = "git 추적" if tracked(root, cs) else ("있음·추적 안 됨" if (root / cs).exists() else "없음")
        lines.append(f"- changeset: `{cs}` ({state})")
        if state != "git 추적":
            warnings.append(f"changeset {cs}")

    if plan is not None:
        steps, paths = plan_files(plan)
        untracked, ignored_paths = [], []
        for p in paths:
            if (root / p).exists() and not tracked(root, p):
                (ignored_paths if ignored(root, p) else untracked).append(p)
        absent = [p for p in paths if not (root / p).exists()]

        def shown(xs: list[str]) -> str:
            return ", ".join(f"`{p}`" for p in xs[:5]) + (f" 외 {len(xs) - 5}개" if len(xs) > 5 else "")

        ok_n = len(paths) - len(untracked) - len(ignored_paths) - len(absent)
        line = f"- 산출물 추적: 완료 step {steps}개의 Files {len(paths)}개 중 git 추적 {ok_n}개"
        if untracked:
            line += f" · 있는데 추적 안 됨 {len(untracked)}개 — {shown(untracked)}"
            warnings.append("산출물 추적")
        if ignored_paths:
            # gitignore 대상은 추적할 방법이 없다 — 경고가 아니라 안내로 둔다
            line += f" · gitignore 대상 {len(ignored_paths)}개 — {shown(ignored_paths)}"
        if absent:
            # 교차 레포 계획서는 다른 레포 경로를 Files 에 적는다 — 경고가 아니라 안내로 둔다
            line += f" · 이 레포에 없음 {len(absent)}개(교차 레포 파일이 아니면 확인) — {shown(absent)}"
        lines.append(line)
    return "\n".join([START, *lines, END]), warnings


def write_block(report: Path, block: str) -> None:
    text = report.read_text(encoding="utf-8-sig")
    if START in text and END in text:
        pre, rest = text.split(START, 1)
        post = rest.split(END, 1)[1]
        new = pre + block + post
    else:
        m = EVIDENCE_HEADING.search(text)
        if not m:
            raise SystemExit(f"report_evidence: `## 3. 증거` 제목이 없다: {report}")
        new = text[: m.end()] + "\n" + block + text[m.end():]
    report.write_text(new, encoding="utf-8", newline="\n")


def block_head(text: str) -> str | None:
    """노트 안 자동 블록의 기준 HEAD (report_close 가 쓴다). 블록이 없으면 None."""
    if START not in text or END not in text:
        return None
    inner = text.split(START, 1)[1].split(END, 1)[0]
    m = HEAD_LINE.search(inner)
    return m.group(1) if m else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--base", required=True, help="milestone 시작 직전 커밋")
    p.add_argument("--plan", type=Path)
    p.add_argument("--changeset", action="append", default=[])
    p.add_argument("--write", type=Path, help="완료 노트 — 블록을 넣거나 갈아끼운다")
    a = p.parse_args(argv)
    root = a.root.resolve()
    plan = a.plan if a.plan is None or a.plan.is_absolute() else root / a.plan
    report = a.write if a.write is None or a.write.is_absolute() else root / a.write
    try:
        block, warnings = build(root, a.base, plan, a.changeset, report)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    if report is not None:
        write_block(report, block)
        print(f"report_evidence: {report} §3 자동 블록 갱신")
    print(block)
    if warnings:
        print("경고: " + " · ".join(warnings) + " — 고치고 다시 돌린다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
