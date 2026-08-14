#!/usr/bin/env python3
"""완료 노트 내구성 점검·교정 — `archive/reports/` 가 gitignore 로 삼켜지는 결함을 잡는다.

배치 규약은 완료 노트를 `archive/reports/<date>-<id>-<slug>.md` 에 두고 이를
milestone 완료의 정본 증거로 삼는다. 그런데 여러 레포가 `archive/` 를 *폐기물 창고*
(dead-scripts·retired-docs)로 먼저 쓰고 있었고 `.gitignore` 에 `archive/` 를 통째로
넣어 뒀다. 두 용법이 같은 폴더명을 공유하는 바람에, close 는 성공하는데 보고서는
로컬에만 남고 ROADMAP 의 `evidence=` 링크가 원격에서 깨진다 (2026-07-23 실측:
the-orchestration-repo OC1).

이 스크립트는 그 결함을 레포 단위·플릿 단위로 찾아 `!archive/reports/` 예외를 넣는다.
폐기물은 계속 무시하고 완료 노트만 추적 대상으로 되살리는 최소 개입이다.

용례:
    python fix_report_durability.py --root .                 # 이 레포 점검(읽기 전용)
    python fix_report_durability.py --root . --apply         # 이 레포 교정
    python fix_report_durability.py --fleet ~/projects       # 전 레포 점검
    python fix_report_durability.py --fleet ~/projects --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROBE = "archive/reports/.probe.md"
JUNK_PROBE = "archive/.junk-probe"   # 폐기물은 계속 무시돼야 한다
COMMENT = [
    "",
    "# 완료 노트는 폐기물이 아니라 milestone 완료의 정본 증거다 (하네스 배치 규약).",
    "# archive/ 는 계속 무시하되 완료 노트만 추적한다.",
]
NEGATION = "!archive/reports/"
# git 은 *제외된 디렉터리* 안의 파일을 다시 포함하지 못한다.
# 따라서 `archive/` 가 아니라 `archive/*` 로 자식만 제외해야 negation 이 먹는다.
DIR_RULE_OLD = {"archive/", "archive", "/archive/", "/archive"}
DIR_RULE_NEW = "archive/*"
STALE = {"!archive/", "!archive/reports/**", "!/archive/"}


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)


def is_git_repo(root: Path) -> bool:
    try:
        out = run(["git", "rev-parse", "--is-inside-work-tree"], root)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() == "true"


def ignored(root: Path, rel: str) -> bool:
    """rel 경로가 gitignore 로 무시되는가."""
    try:
        return run(["git", "check-ignore", "-q", rel], root).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def diagnose(root: Path) -> dict:
    """레포 하나의 완료 노트 내구성 상태."""
    st = {"root": root, "git": False, "broken": False, "overbroad": False,
          "existing_reports": 0, "untracked_reports": 0, "note": ""}
    if not is_git_repo(root):
        st["note"] = "git 레포 아님 — 대상 외"
        return st
    st["git"] = True
    st["broken"] = ignored(root, PROBE)
    # 두 번째 결함 유형: 과잉 negation. `!archive/` 처럼 창고 문을 통째로 여는 규칙이
    # 남아 있으면 완료 노트는 살아나지만 폐기물까지 추적 대상이 된다 (2026-07-23 자체 사고).
    gi = root / ".gitignore"
    if gi.exists():
        rules = {ln.strip() for ln in gi.read_text(encoding="utf-8").splitlines()}
        if rules & STALE:
            st["broken"] = True
            st["overbroad"] = True
    reports = root / "archive" / "reports"
    if reports.is_dir():
        files = sorted(p for p in reports.glob("*.md") if p.is_file())
        st["existing_reports"] = len(files)
        if files:
            rels = [str(p.relative_to(root)).replace("\\", "/") for p in files]
            try:
                # -z: 비ASCII 파일명을 git 이 따옴표로 감싸 오탐하는 것을 막는다
                # (2026-07-23 comento-accounting 한글 보고서 false positive)
                out = run(["git", "ls-files", "-z", "--"] + rels, root)
                tracked = {s for s in out.stdout.split(chr(0)) if s}
            except (OSError, subprocess.SubprocessError):
                tracked = set()
            st["untracked_reports"] = len([r for r in rels if r not in tracked])
    return st


def apply_fix(root: Path) -> str:
    """`archive/` 규칙을 `archive/*` 로 바꾸고 `!archive/reports/` 를 넣는다.

    핵심: git 은 제외된 *디렉터리* 안을 들여다보지 않으므로 `archive/` 를 그대로 두면
    어떤 negation 도 먹지 않는다. 자식만 제외(`archive/*`)해야 폐기물은 계속 무시하면서
    완료 노트만 되살릴 수 있다.
    """
    gi = root / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []

    # 이전 시도가 남긴 잘못된 negation 제거.
    # NEGATION 도 함께 걷어낸다 — gitignore 는 *마지막에 매칭된 규칙*이 이기므로
    # negation 이 `archive/*` 보다 앞에 있으면 무력하다(2026-07-23 knowledge-graph 실측).
    # 아래에서 항상 파일 끝에 다시 붙인다.
    drop = STALE | {NEGATION} | {c.strip() for c in COMMENT if c.strip()}
    lines = [ln for ln in lines if ln.strip() not in drop]

    replaced = False
    out = []
    for ln in lines:
        if ln.strip() in DIR_RULE_OLD:
            out.append(DIR_RULE_NEW)
            replaced = True
        else:
            out.append(ln)
    lines = out

    if not replaced and DIR_RULE_NEW not in [ln.strip() for ln in lines]:
        lines.append(DIR_RULE_NEW)
    lines += COMMENT + [NEGATION]   # 항상 파일 끝 — 마지막 규칙이 이긴다

    nl = chr(10)
    gi.write_text(nl.join(lines).rstrip(nl) + nl, encoding="utf-8")

    if ignored(root, PROBE):
        return "예외를 넣었으나 보고서가 여전히 무시됨 — .gitignore 를 수동 확인할 것"
    if not ignored(root, JUNK_PROBE):
        return "경고: 완료 노트는 살아났으나 archive/ 폐기물까지 노출됨 — 수동 확인 필요"
    return "교정 완료 (폐기물은 계속 무시)"


def report(st: dict, apply: bool) -> bool:
    """한 레포 결과 출력. 결함이 남아 있으면 True."""
    name = st["root"].name
    if not st["git"]:
        return False
    if not st["broken"]:
        extra = ""
        if st["untracked_reports"]:
            extra = f" (미커밋 보고서 {st['untracked_reports']}건 — 커밋 필요)"
        print(f"  OK    {name}{extra}")
        return False
    detail = f"보고서 {st['existing_reports']}건" if st["existing_reports"] else "보고서 없음"
    if st.get("overbroad"):
        detail += ", 과잉 negation"
    if apply:
        result = apply_fix(st["root"])
        still = ignored(st["root"], PROBE) or not ignored(st["root"], JUNK_PROBE)
        mark = "FIXED" if not still else "FAIL "
        print(f"  {mark} {name}: archive/reports/ 가 무시됨 ({detail}) → {result}")
        return still
    kind = "archive/ negation 이 과잉 — 폐기물까지 노출" if st.get("overbroad") else "archive/reports/ 가 gitignore 로 무시됨"
    print(f"  BROKEN {name}: {kind} ({detail})")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None, help="단일 레포 경로")
    ap.add_argument("--fleet", type=Path, default=None, help="레포들의 부모 폴더")
    ap.add_argument("--apply", action="store_true", help="실제로 .gitignore 를 고친다")
    args = ap.parse_args(argv)

    if not args.root and not args.fleet:
        args.root = Path(".")

    roots: list[Path] = []
    if args.root:
        roots.append(args.root.resolve())
    if args.fleet:
        base = args.fleet.expanduser().resolve()
        roots += sorted(p for p in base.iterdir() if (p / ".git").exists())

    print(f"완료 노트 내구성 점검 — 대상 {len(roots)}개"
          f"{' (교정 모드)' if args.apply else ' (읽기 전용)'}")
    broken = 0
    for r in roots:
        if report(diagnose(r), args.apply):
            broken += 1
    if broken:
        print(f"\n결함 {broken}건 남음."
              f"{'' if args.apply else '  --apply 로 교정한다.'}")
        return 1
    print("\n전부 정상 — 완료 노트가 git 에 남는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
