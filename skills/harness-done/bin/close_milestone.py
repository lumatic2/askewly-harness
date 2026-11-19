#!/usr/bin/env python3
"""마감 닫기 한 번에 — report_close → ROADMAP complete → 계획서 archive 이동 → 포인터 수리 → (150줄 초과면) compact.

harness-done 5·6단계를 명령 4~5개로 따로 부르던 것을 묶는다(2026-11-16). 각 단계는 원래 스크립트를
그대로 부르고, 실패하면 그 자리에서 멈춰 어느 단계인지 찍는다. 이미 끝난 단계(계획서가 이미 archive 에
있음)는 건너뛴다. 검사 규칙은 각 스크립트가 소유한다 — 여기서 새로 판정하지 않는다.

Usage:
  close_milestone.py --root <레포> --report <완료 노트> --task-id <work-id> --milestone <M-id>
                     --summary "<사용자용 한 문장>" [--plan <계획서>] [--roadmap-summary "<한 줄>"]

exit: 0 = 전부 끝 / 1 = 어느 단계가 실패(출력에 단계 이름) / 2 = 사용법 오류
"""

from __future__ import annotations

import argparse
import hashlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "harness-run" / "scripts"
MAX_LINES = 150
BRANCH_FILE = ".harness/fanout/branch.json"


def run(step: str, cmd: list[str], cwd: Path) -> bool:
    print(f"[close] {step}: {' '.join(cmd[1:])}")
    out = subprocess.run(cmd, cwd=str(cwd), text=True, encoding="utf-8", errors="replace",
                         capture_output=True)
    for stream in (out.stdout, out.stderr):
        if stream.strip():
            print(stream.rstrip())
    if out.returncode != 0:
        print(f"[close] 실패 — {step} (exit {out.returncode}). 고친 뒤 같은 명령을 다시 돌린다 — 끝난 단계는 건너뛴다.",
              file=sys.stderr)
        return False
    return True


def tracked(root: Path, rel: str) -> bool:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "--", rel], capture_output=True, text=True)
    return out.returncode == 0 and bool(out.stdout.strip())


def status_entries(root: Path) -> dict[str, tuple[str, str | None]] | None:
    """`git status` 를 파일 단위로 읽는다: 경로 → (XY 두 글자, 이름이 바뀐 경우 옛 경로). git 을 못 읽으면 None."""
    out = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return None
    entries: dict[str, tuple[str, str | None]] = {}
    parts = iter(out.stdout.split("\0"))
    for part in parts:
        if len(part) < 4:
            continue
        xy, path = part[:2], part[3:]
        entries[path] = (xy, next(parts, None) if xy[0] in "RC" else None)
    return entries


def digests(root: Path, entries: dict[str, tuple[str, str | None]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in entries or {}:
        try:
            out[rel] = hashlib.sha1((root / rel).read_bytes()).hexdigest()
        except OSError:
            out[rel] = "gone"
    return out


def ignored(root: Path, rel: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", rel],
                          capture_output=True).returncode == 0


def print_commit_commands(root: Path, milestone: str, before: dict[str, str], fixed: list[str]) -> None:
    """이 마감에서 스크립트가 바꾼 파일 중 `git add` 가 필요한 것만 골라 그대로 실행되는 명령을 찍는다.

    에이전트가 경로를 손으로 적다가 이미 없는 옛 `plans/<파일>` 이나 gitignore 된 경로를 넣어 `git add` 가
    통째로 실패하던 것을 막는다(2026-11-17 이후 마감 10건 중 6건). 스스로 커밋하지는 않는다."""
    after = status_entries(root)
    if after is None:
        print("[close] 끝 — git 상태를 읽지 못해 경로 목록을 만들지 못했다. 노트·ROADMAP·계획서 이동을 pathspec 커밋한다")
        return
    now = digests(root, after)
    # 고정 후보(노트·ROADMAP·BACKLOG·옮긴 계획서) + 이 실행 동안 내용이 바뀐 파일(포인터 수리 등). 하네스 상태는 뺀다
    cands = {c for c in fixed if c} | {p for p, d in now.items() if before.get(p) != d}
    cands = {c for c in cands if c != ".harness" and not c.startswith(".harness/")}
    to_add, commit_paths, moves, not_trackable = [], [], [], []
    for rel in sorted(cands):
        if rel in after:
            xy, orig = after[rel]
            if xy[0] in "RC" and orig:
                moves.append((orig, rel))
                commit_paths.append(orig)
            if xy[1] != " ":  # 작업 트리에 스테이징 안 된 변경이 있다 = add 가 필요하다
                to_add.append(rel)
            commit_paths.append(rel)
        elif (root / rel).exists() and ignored(root, rel):
            not_trackable.append(rel)
    print("[close] 끝 — 아래 명령을 그대로 실행해 마감 커밋을 만든다 (push 는 따로)")
    for old, new in moves:
        print(f"[close] 이동은 이미 스테이징됨: {old} → {new} (add 목록에 넣지 않는다)")
    if not_trackable:
        print("[close] gitignore 대상이라 추적할 수 없어 커밋에서 뺀다: " + ", ".join(not_trackable))
    if not commit_paths:
        print("[close] 커밋할 변경이 없다")
        return
    if to_add:
        print("git add -- " + " ".join(shlex.quote(p) for p in to_add))
    print(f"git commit -m {shlex.quote(f'chore(roadmap): {milestone} 완료')} -- "
          + " ".join(shlex.quote(p) for p in sorted(set(commit_paths))))


def ledger_has_completion(root: Path, task_id: str) -> bool:
    ledger = root / ".harness" / "execution-ledger.jsonl"
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError:
        return False
    return any('"task_completed"' in ln and f'"{task_id}"' in ln for ln in text.splitlines())


def move_plan(root: Path, plan: Path) -> tuple[bool, Path]:
    plan = plan if plan.is_absolute() else root / plan
    dest = root / "archive" / "plans" / plan.name
    if not plan.exists() and dest.exists():
        print(f"[close] 계획서 이동: 이미 archive 에 있다 — {dest.relative_to(root).as_posix()}")
        return True, dest
    if not plan.exists():
        print(f"[close] 실패 — 계획서가 없다: {plan}", file=sys.stderr)
        return False, dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    rel = plan.relative_to(root).as_posix()
    if tracked(root, rel):
        ok = subprocess.run(["git", "-C", str(root), "mv", rel, dest.relative_to(root).as_posix()]).returncode == 0
        if not ok:
            print(f"[close] 실패 — git mv {rel}", file=sys.stderr)
            return False, dest
    else:
        shutil.move(str(plan), str(dest))
    print(f"[close] 계획서 이동: {rel} → {dest.relative_to(root).as_posix()}")
    return True, dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--milestone", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--plan", type=Path)
    p.add_argument("--roadmap-summary", default=None, help="ROADMAP 한 줄 (기본 = --summary)")
    p.add_argument("--branch", action="store_true",
                   help="팬아웃 갈래 닫기 — report_close 만 돌리고 ROADMAP·계획서·compact 는 건드리지 않는다")
    a = p.parse_args(argv)
    root = a.root.resolve()
    py = sys.executable
    report = a.report if a.report.is_absolute() else root / a.report
    has_deliverable = (root / BRANCH_FILE).is_file()
    if a.branch and not has_deliverable:
        print(f"[close] 거부 — --branch 는 갈래 전달물({BRANCH_FILE})이 있는 워크트리에서만 쓴다", file=sys.stderr)
        return 2
    if has_deliverable and not a.branch:
        print(f"[close] 거부 — 갈래 워크트리({BRANCH_FILE} 있음)에서는 --branch 로 닫는다. "
              "ROADMAP·계획서는 메인이 닫는다", file=sys.stderr)
        return 2
    evidence = report.relative_to(root).as_posix() if report.is_relative_to(root) else str(report)
    before = digests(root, status_entries(root))  # 끝에서 이 실행이 바꾼 파일을 가려내는 기준
    fixed = [evidence if report.is_relative_to(root) else "", "ROADMAP.md"]

    if ledger_has_completion(root, a.task_id):
        print(f"[close] report_close: 이미 닫혔다({a.task_id}) — 건너뛴다")
    elif not run("report_close", [py, str(SCRIPTS / "report_close.py"), str(report), "--task-id", a.task_id,
                                  "--root", str(root), "--summary", a.summary], root):
        return 1

    if a.branch:
        note = str(report)
        print("[close] 갈래 닫기 — roadmap·계획서·compact 건너뜀. 아래 명령으로 메인에 완료를 알린다(직접 실행)")
        print(f"python {SCRIPTS / 'fanout.py'} ready --root {shlex.quote(str(root))} --note {shlex.quote(note)}")
        return 0

    roadmap = root / "ROADMAP.md"
    if roadmap.exists():
        if not run("roadmap complete", [py, str(SCRIPTS / "roadmap_sync.py"), "complete", "--milestone", a.milestone,
                                        "--evidence", evidence, "--summary", a.roadmap_summary or a.summary], root):
            return 1
    else:
        print("[close] ROADMAP.md 없음 — complete·compact 건너뜀")

    if a.plan is not None:
        ok, dest = move_plan(root, a.plan)
        if not ok:
            return 1
        fixed.append(dest.relative_to(root).as_posix())
        if roadmap.exists() and not run("repair-plan-pointers",
                                        [py, str(SCRIPTS / "roadmap_sync.py"), "repair-plan-pointers"], root):
            return 1

    if roadmap.exists():
        lines = len(roadmap.read_text(encoding="utf-8").splitlines())
        if lines > MAX_LINES:
            if not run("compact", [py, str(SCRIPTS / "roadmap_sync.py"), "compact", "--max-lines", str(MAX_LINES),
                                   "--backlog", "docs/BACKLOG.md"], root):
                return 1
            fixed.append("docs/BACKLOG.md")
        else:
            print(f"[close] compact: ROADMAP {lines}줄 ≤ {MAX_LINES} — 건너뜀")
    print_commit_commands(root, a.milestone, before, fixed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
