#!/usr/bin/env python3
"""ROADMAP 위생 점검 — 세션 마감이 총괄 뷰 실종을 잡는다 (M3 2026-08-19).

읽기 전용·비파괴이고 **항상 exit 0** 이다. 이 게이트 때문에 세션 마감이 막히면
안 된다 — 원래 막으려던 사고(레포가 총괄에서 조용히 사라지는 것)보다 마감 차단이
더 나쁘다.

판정 어휘의 정본은 이 파일이 아니라 같은 폴더의 `roadmap_parse.py` 다. 재구현하지
않고 importlib 로 불러 쓴다 — 파서와 다른 눈으로 보면 게이트가 의미가 없다.
(2026-09-21 이관: 원래 `the-orchestration-repo/scripts/portfolio_status.py` 였으나 그
총괄 뷰가 은퇴하면서 파서만 여기로 왔다. 어휘와 동작은 그대로다.)

**섹션 배치 어휘의 정본도 이 파일이 아니다** (M5 2026-08-20). 무엇이 진행 계열
섹션인지는 `harness-run/scripts/roadmap_sync.py` 가 소유하고 여기서 import 해 쓴다.
구 판본은 "그 판정은 재사용할 수 없다 — `find_blocks()` 가 상위 섹션을 안 내보낸다"는
예외를 달고 정규식 사본을 들고 있었는데, M5 가 그쪽에 조상 헤딩 추적(`section_spans`)을
만들면서 예외가 해소됐다. 사본을 남기면 **이 게이트가 지적하는 것과 `relocate` 가
실제로 옮기는 것이 갈라져** 안내문이 거짓이 된다.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import os
import subprocess
import sys
from pathlib import Path

ROADMAP_PARSE = Path(__file__).resolve().parent / "roadmap_parse.py"

# 배포 레이아웃과 소스 트리 셋 다에서 성립한다:
#   <플러그인 루트>/skills/session-end/bin/  → <플러그인 루트>/skills/harness-run/scripts/
#   <플러그인 루트>/skills/session-end/bin/   → <플러그인 루트>/skills/harness-run/scripts/
#   promoted/session-end/bin/          → promoted/harness-run/scripts/
# 스테이징 이명 레인(`harness-run-stg`)은 셋째 후보로 찾고, 그래도 어긋나면 `--sync-scripts` 로 준다.
# h-e M33 step-5 (F8): 종전엔 harness-run 경로 하나를 고정해 `-stg` 배포본에서 섹션 판정이 조용히 꺼졌다.


def find_sync_scripts(here: Path | None = None, env: "dict[str, str] | None" = None) -> Path:
    """roadmap_sync.py 가 있는 디렉터리 — ① $HARNESS_SCRIPTS ② 형제 harness-run ③ 형제 harness-run-stg.
    셋 다 없으면 ② 를 돌려주되 stderr 에 한 줄 경고한다(조용한 무동작 금지)."""
    here = (here or Path(__file__)).resolve()
    env = os.environ if env is None else env
    candidates = []
    if env.get("HARNESS_SCRIPTS"):
        candidates.append(Path(env["HARNESS_SCRIPTS"]))
    base = here.parents[2]
    candidates += [base / "harness-run" / "scripts", base / "harness-run-stg" / "scripts"]
    for c in candidates:
        if (c / "roadmap_sync.py").is_file():
            return c
    print(f"roadmap_hygiene: roadmap_sync.py 를 못 찾음 — 후보 {[str(c) for c in candidates]} · 섹션 판정은 생략된다", file=sys.stderr)
    return candidates[-2] if len(candidates) >= 2 else candidates[0]


SYNC_SCRIPTS = find_sync_scripts()

HEADING_RE = re.compile(r"^#{2,4}\s+(?P<title>.+?)\s*$")


def load_roadmap_sync(scripts_dir: Path = SYNC_SCRIPTS):
    """배치 어휘 정본을 모듈로 불러온다. 실패는 호출자가 **그 항목만** 생략으로 처리한다."""
    path = Path(scripts_dir) / "roadmap_sync.py"
    spec = importlib.util.spec_from_file_location("_roadmap_sync", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("모듈을 불러올 수 없다: {}".format(path))
    module = importlib.util.module_from_spec(spec)
    # sys.modules 등록이 필수다 — roadmap_sync 는 `@dataclass` 를 쓰는데, dataclasses 가
    # 필드 타입을 풀 때 `sys.modules[cls.__module__]` 를 찾는다. 등록 없이 exec 하면
    # 거기서 AttributeError 로 터진다(2026-08-20 실측 — 배치 판정이 통째로 꺼졌다).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_roadmap_parser(path: Path = ROADMAP_PARSE):
    """ROADMAP 파서를 모듈로 불러온다. 실패는 호출자가 생략으로 처리한다."""
    spec = importlib.util.spec_from_file_location("_roadmap_parse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("모듈을 불러올 수 없다: {}".format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_name(repo: Path) -> str:
    """INDEX.md 조회용 레포 이름 = main 체크아웃 폴더명.

    linked worktree 에서 cwd basename 을 쓰면 브랜치 폴더명이 잡혀 kind 태그 조회가
    조용히 빗나간다. `git worktree list` 첫 행이 main 체크아웃이다.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return repo.resolve().name
    for line in out.splitlines():
        if line.startswith("worktree "):
            return Path(line.split(" ", 1)[1].strip()).name
    return repo.resolve().name


def section_titles(lines: list[str]) -> dict[int, str]:
    """줄 번호(0-indexed) → 그 줄이 속한 최근 `##` 섹션 제목."""
    mapping: dict[int, str] = {}
    current = ""
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and line.startswith("## "):
            current = match.group("title")
        mapping[idx] = current
    return mapping


def misplaced_terminal(
    lines: list[str], milestones: list[dict], terminal: set, in_progress_re
) -> list[str]:
    """진행 섹션 아래에 앉은 종결 마커. `in_progress_re` 는 roadmap_sync 가 소유한다."""
    sections = section_titles(lines)
    out = []
    for ms in milestones:
        if ms.get("status") not in terminal:
            continue
        idx = (ms.get("line") or 1) - 1
        title = sections.get(idx, "")
        if title and in_progress_re.search(title):
            out.append('{} ({}) — "## {}" 아래'.format(ms.get("id"), ms.get("status"), title))
    return out


def build_report(roadmap: Path, repo: Path, ps, sync_scripts: Path = SYNC_SCRIPTS) -> tuple:
    """(출력 줄, 발견 건수). 발견 0 이면 호출자가 한 줄 PASS 로 마무리한다."""
    lines = ps.read_text(roadmap).splitlines()
    _goal, milestones, parked = ps.parse_roadmap(roadmap)

    active = [m for m in milestones if m.get("status") in ps.ACTIVE_STATUSES]

    body: list[str] = []
    found = 0

    # ① 종결 마커가 진행 섹션에 앉아 있다.
    #
    # 배치 어휘는 roadmap_sync 가 소유한다. **import 실패는 이 항목만 생략**하고
    # 나머지 발견은 그대로 낸다 — 여기서 예외를 위로 흘리면 main() 의 포괄 except 가
    # 위생 점검 **전체**를 "생략" 한 줄로 조용히 끄기 때문이다(그 침묵이 원래 이
    # 게이트가 막으려던 사고와 같은 모양이다).
    try:
        rs = load_roadmap_sync(sync_scripts)
        misplaced = misplaced_terminal(
            lines, milestones, ps.TERMINAL_STATUSES, rs.IN_PROGRESS_HEADING_RE
        )
    except Exception as exc:  # noqa: BLE001 — 이 항목만 포기한다
        misplaced = []
        # 발견으로 센다. 안 세면 다른 발견이 0 인 레포에서 이 줄이 통째로 버려져
        # (build_report 가 found==0 이면 빈 보고서를 돌려준다) 판정이 꺼진 사실이
        # PASS 로 보인다 — 이 게이트가 막으려는 침묵과 정확히 같은 모양이다.
        found += 1
        body.append("[섹션 오배치] **판정이 꺼졌다** — 배치 어휘를 못 읽었다 ({}: {})".format(
            type(exc).__name__, exc))
        body.append("  → harness-run 배포본이 온전한지 확인한다. 이 회차의 오배치 결과는 신뢰할 수 없다.")
    if misplaced:
        found += len(misplaced)
        body.append("[섹션 오배치] 종결 마커가 진행 섹션에 남아 있다 — 스크래퍼는 헤딩을 안 읽어 집계는 맞지만 사람이 오독한다")
        body += ["  - " + item for item in misplaced]
        body.append("  → `python \"$HARNESS_SCRIPTS/roadmap_sync.py\" relocate` 로 Completed 섹션으로 옮긴다(먼저 `--dry-run` 으로 대상을 본다). BACKLOG 아카이브는 다른 처분이다 — 그쪽은 마커째 제거이고 `/harness-done` 의 `compact` 가 소유한다.")

    # ② **삭제됨 (2026-08-20 사용자 확정).** 구 판본은 진행 중 milestone 이 없으면
    #    발견으로 세고 세 갈래 처분(승격/PARK/면제)을 요구했다. 그건 결함이 아니라
    #    **정상 상태**다 — 다음이 있으면 그걸 하고 없으면 멈추는 것이고, 그 판단은
    #    사용자 소유다. 게다가 방치 판정은 주간 PORTFOLIO 리뷰의 판정 대기 큐가 이미
    #    본다. 매 세션 마감마다 같은 처분을 요구하는 것은 잔소리였고, 잔소리는 사람이
    #    /session-end 를 피하게 만들어 게이트 자체를 무력화한다(이 파일 계약 ⓐ).
    #
    #    그 갈래가 유일하게 혼자 잡던 신호 하나(**status 속성이 아예 없는 마커**)는
    #    아래 ④ 로 옮겼다. 나머지 두 갈래는 판정이 아니라 안내였다.
    #
    #    남은 사용처가 없어진 것: `repo_name()`·`--repo`·`ps.load_kinds()`·
    #    `QUEUE_EXEMPT_KINDS`·`DECISION_QUEUE_DAYS`. 호출자가 `--repo` 를 계속 넘기므로
    #    인자와 헬퍼는 그대로 두고 판정에서만 뺀다.

    # ③ 마커 status 와 체크박스 불일치.
    mismatched = [m for m in milestones if ps.checkbox_mismatch(m)]
    if mismatched:
        found += len(mismatched)
        body.append("[체크박스 불일치] 마커 status 와 `- Status:` 체크박스가 어긋난다")
        body += [
            "  - {}: status={} · 체크박스 {}".format(m.get("id"), m.get("status"), m.get("checkbox"))
            for m in mismatched
        ]

    # ④ 비정본 status 어휘. 두 종류를 구분한다 — 총괄이 흡수하는 변종(`in_progress`)과
    #    아예 안 읽히는 값. 하나로 묶으면 "진행으로 안 센다"가 흡수 변종에 대해 거짓이
    #    된다 (2026-08-19 코드 리뷰 적발).
    absorbed = [
        m for m in milestones
        if m.get("status") in ps.ACTIVE_STATUSES and m.get("status") not in ps.CANONICAL_STATUSES
    ]
    # status 속성이 아예 없는 마커도 여기서 잡는다 (구 ② 에서 이관, 2026-08-20).
    # 총괄은 이 마커를 진행으로도 종결로도 못 읽어서 레포가 조용히 사라진다.
    unknown = [
        m for m in milestones
        if not m.get("status")
        or (m.get("status") not in ps.CANONICAL_STATUSES
            and m.get("status") not in ps.ACTIVE_STATUSES)
    ]
    canonical = "·".join(sorted(ps.CANONICAL_STATUSES))
    if absorbed:
        found += len(absorbed)
        body.append("[비정본 status 어휘] 총괄이 진행으로 흡수하긴 하지만 정본 어휘가 아니다 (정본: {})".format(canonical))
        body += ["  - {}: `{}` → `active`".format(m.get("id"), m.get("status")) for m in absorbed]
    if unknown:
        found += len(unknown)
        body.append("[비정본 status 어휘] 총괄이 읽지 못하는 값이다 (정본: {})".format(canonical))
        body += ["  - {}: `{}`".format(m.get("id"), m.get("status") or "없음") for m in unknown]

    if not found:
        return [], 0

    header = "ROADMAP 위생: 발견 {}건 (active {})".format(found, len(active))
    tail = "이 게이트는 파일을 수정하지 않는다 — 발견은 HANDOFF.md 주의점으로 넘긴다."
    return [header, ""] + body + ["", tail], found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", default="ROADMAP.md")
    parser.add_argument("--repo", default=".", help="INDEX.md kind 태그 조회에 쓰는 레포 루트")
    parser.add_argument("--parser", "--portfolio-status", dest="parser",
                        default=str(ROADMAP_PARSE))
    parser.add_argument("--sync-scripts", default=str(SYNC_SCRIPTS),
                        help="배치 어휘를 가진 roadmap_sync.py 가 있는 디렉터리 "
                             "(스테이징 이명 레인처럼 기본 경로가 어긋나는 자리에서 준다)")
    args = parser.parse_args(argv)

    roadmap = Path(args.roadmap)
    if not roadmap.exists():
        print("ROADMAP 위생: 생략 — {} 없음".format(roadmap))
        return 0

    # D4: 임포트만이 아니라 **점검 중 모든 예외**를 생략으로 흘린다. 여기서 예외가
    # 새면 세션 마감이 막힌다. (구 판본은 the-orchestration-repo/manifests/projects.json
    # 을 읽다 터지는 경로가 있었다 — 그 의존은 2026-09-21 에 사라졌지만, 예외를
    # 삼키는 계약 자체는 이 게이트의 존재 이유라 유지한다.)
    try:
        ps = load_roadmap_parser(Path(args.parser))
        report, found = build_report(roadmap, Path(args.repo), ps, Path(args.sync_scripts))
        if not found:
            _goal, milestones, _parked = ps.parse_roadmap(roadmap)
            active = [m for m in milestones if m.get("status") in ps.ACTIVE_STATUSES]
            print("ROADMAP 위생: PASS (active {})".format(len(active)))
            return 0
    except Exception as exc:  # noqa: BLE001 — 마감을 막지 않는 것이 이 게이트의 계약
        print("ROADMAP 위생: 생략 — {}: {}".format(type(exc).__name__, exc))
        return 0

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
