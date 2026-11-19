#!/usr/bin/env python3
"""워크트리 범위 게이트 (M29 2026-09-03) — 상태·인덱스 파일을 워크트리가 쓰고 있는지 본다.

워크트리 규약 §2.5 ③「쓰기 주체 분리」의 기계판. 상태·인덱스 파일(`ROADMAP.md`·
`changesets/README.md`·`docs/BACKLOG.md`)은 **거두는 메인 체크아웃이 쓴다** — 워크트리가
같이 쓰면 병합 때 사람이 고쳐야 한다. `merge=union` 은 답이 아니다: `changesets/README.md` 는
`#` 전역 순번을 가진 표라 union 이면 번호가 겹치고, `ROADMAP.md` 는 `Status: [x]` 를
in-place 로 고친다.

⚠ **훅으로 만들지 않는다.** 비결정 게이트가 정당한 작업을 막는 실패가 반복 관측됐다.
이것은 절차가 부르는 검사이고, 사람이 판단을 뒤집을 수 있다.

워크트리 판정 (2026-09-03 실측 — 4개 위치에서 확인):
    `git rev-parse --path-format=absolute --git-dir` == `--git-common-dir`  → 메인
⚠ 「`--git-common-dir` 이 `.git` 과 다르면 워크트리」로 판정하면 **메인 체크아웃의 하위폴더에서
오탐한다**(거기선 상대경로 `../.git` 이 나온다). `--path-format=absolute` 로 양쪽을 절대경로로
받아 비교하는 것이 정본이다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

# 메인만 쓰는 상태·인덱스 파일 (§2.5 ③)
GUARDED = (
    "ROADMAP.md",
    "changesets/README.md",
    "docs/BACKLOG.md",
    "BACKLOG.md",            # 구 레포는 루트에 둔다
    # HANDOFF 는 글로벌 규약이 「main 체크아웃에서만」으로 못 박았고 session-end 가 단독
    # 커밋+push 한다 — 워크트리가 같이 쓰면 ROADMAP 과 정확히 같은 충돌 계열이다(2026-09-03 리뷰).
    "HANDOFF.md",
)
# GUARDED 는 **정확 일치** 목록이다 — 그래서 허용 목록이 따로 필요 없다.
# `changesets/<id>/README.md`·`plans/`·`archive/plans/`·`archive/reports/`(§2.5 ④ 의 마감
# 산출물)는 구조적으로 걸리지 않는다. 허용 목록을 따로 두면 GUARDED 와 우선순위가 엉켜
# `changesets/README.md` 가 `changesets/` 접두에 먹히는 사고가 난다.


def git(*args: str, root: str = ".") -> str:
    res = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        sys.exit(f"git {' '.join(args)} 실패: {res.stderr.strip()}")
    return res.stdout.strip()


def is_worktree(root: str) -> bool:
    out = git("rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", root=root)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) != 2:
        sys.exit(f"rev-parse 출력이 2줄이 아니다 — 판정 불가:\n{out}")
    git_dir, common_dir = lines
    return git_dir != common_dir


def changed_paths(root: str) -> list[str]:
    """staged + unstaged 를 모두 본다 (M29 권고 7 — 어느 쪽이든 병합 대상이 된다)."""
    paths: list[str] = []
    for line in git("status", "--porcelain", root=root).splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        # rename 은 **양쪽 다** 본다 (2026-09-03 리뷰) — 목적지만 보면
        # `git mv ROADMAP.md ROADMAP.old.md` 가 통과한다(원본이 사라진 것도 위반이다).
        parts = [p.strip().strip('"') for p in path.split(" -> ")] if " -> " in path else [path]
        for part in parts:
            paths.append(str(PurePosixPath(part.replace("\\", "/"))))
    return paths


def violations(paths: list[str]) -> list[str]:
    return [p for p in paths if p in GUARDED]


def main() -> int:
    ap = argparse.ArgumentParser(description="워크트리가 상태·인덱스 파일을 쓰고 있는지 검사 (워크트리 규약 §2.5 ③)")
    ap.add_argument("--root", default=".", help="검사할 체크아웃 (기본: 현재 디렉터리)")
    ap.add_argument("--quiet", action="store_true", help="위반이 없으면 아무것도 출력하지 않는다")
    ap.add_argument("--base", default=None,
                    help="이 브랜치와의 merge-base 이후 **커밋된** 변경도 검사한다 (예: master). "
                         "워킹트리만 보면 워크트리가 ROADMAP.md 를 커밋해 버린 뒤로는 영영 통과한다 "
                         "— 정작 병합 때 손으로 푸는 건 그 커밋된 변경이다(2026-09-03 리뷰)")
    args = ap.parse_args()

    if not is_worktree(args.root):
        if not args.quiet:
            print("메인 체크아웃 — 검사 대상 아님 (상태·인덱스 파일은 여기서 쓰는 것이 맞다)")
        return 0

    paths = changed_paths(args.root)
    if args.base:
        base = git("merge-base", args.base, "HEAD", root=args.root)
        for line in git("diff", "--name-only", f"{base}..HEAD", root=args.root).splitlines():
            if line.strip():
                paths.append(str(PurePosixPath(line.strip().replace("\\", "/"))))
    hits = sorted(set(violations(paths)))
    if not hits:
        if not args.quiet:
            print("워크트리 — 상태·인덱스 파일 수정 없음 (OK)")
        return 0

    print("⚠ 워크트리가 메인 소유 파일을 쓰고 있다 (워크트리 규약 §2.5 ③ 쓰기 주체 분리):", file=sys.stderr)
    for p in hits:
        print(f"  - {p}", file=sys.stderr)
    print(
        "\n이 파일들은 **거두는 메인 세션**이 쓴다. 워크트리는 자기 `changesets/<id>/README.md` 에\n"
        "「병합 대기」 절(브랜치명·커밋 수·DoD 자기판정·미해결 항목)을 쓰고 끝낸다(§2.5 ④).\n"
        "되돌리기: git checkout -- " + " ".join(hits),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
