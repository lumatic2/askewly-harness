#!/usr/bin/env python3
"""체크아웃 최신성 게이트 (탐색 첫 도구 호출 자동화, 2026-07-21 MM1 step-3).

구 `/harness` 탐색 첫 단계는 "읽기 전에 낙오 여부를 확인하라"는 **수동 절차**였다. 사람도
에이전트도 그날 그걸 떠올리지 않았고, macair 체크아웃이 origin 대비 104커밋
뒤처진 채 이미 기각된 설계(machine-id overlay)를 회귀로 오진해 되살려 배포했다.
수동 절차를 실행 가능한 검사로 승격한다.

판정 3상태 — 조용한 성공을 만들지 않는다:
- fetch 성공 + behind>0 → **exit 1** (낙오. 동기화 전에는 탐색·판단을 시작하지 않는다)
- fetch 성공 + behind=0 → exit 0 (검증된 최신)
- fetch 실패(오프라인·인증) → exit 0 + "확인 불가" (최신으로 오판하지 않되 작업은 막지 않음)

`--ttl` 은 탐지 사각지대와 정확히 같은 길이다 — 캐시가 유효한 동안 원격이 앞서가면
낙오를 놓친다(2026-07-21 독립 검증 실측). 그래서 캐시로 판정했을 때는 "검증됨"이라
말하지 않고 몇 초 전 기준인지 밝힌다. harness-plan 탐색 권장값은 300초.

원격 ref 만 갱신한다. merge/rebase 는 하지 않으므로 작업 트리는 그대로다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def git(root: Path, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def fetch_age_seconds(root: Path) -> float | None:
    for candidate in (root / ".git" / "FETCH_HEAD", root / "FETCH_HEAD"):
        try:
            return time.time() - candidate.stat().st_mtime
        except OSError:
            continue
    return None


def check(root: Path, ttl_seconds: float = 0) -> dict:
    if not (root / ".git").exists():
        return {"state": "not_a_repo", "behind": 0, "message": "git 저장소가 아니다 — 검사 생략"}

    cached_age = None
    if ttl_seconds > 0:
        age = fetch_age_seconds(root)
        if age is not None and age < ttl_seconds:
            cached_age = age
    if cached_age is None:
        proc = git(root, ["fetch", "--quiet", "--prune"])
        if proc is None or proc.returncode != 0:
            reason = (proc.stderr.strip()[:200] if proc else "fetch timed out")
            return {
                "state": "unknown",
                "behind": 0,
                "message": f"확인 불가 — fetch 실패로 낙오 여부를 판정할 수 없다 ({reason})",
            }

    rev = git(root, ["rev-list", "--count", "HEAD..@{upstream}"])
    if rev is None or rev.returncode != 0:
        return {
            "state": "unknown",
            "behind": 0,
            "message": "확인 불가 — 현재 브랜치에 upstream 이 없다",
        }
    behind = int(rev.stdout.strip() or 0)
    basis = "fetch 로 검증됨" if cached_age is None else f"{int(cached_age)}초 전 fetch 기준(캐시) — 그 이후 원격 변화는 미반영"
    if behind:
        return {
            "state": "stale",
            "behind": behind,
            "cached": cached_age is not None,
            "message": (
                f"낙오 {behind} 커밋 ({basis}) — 동기화 전에는 탐색·판단을 시작하지 않는다. "
                "배포본↔소스 불일치를 회귀로 단정하기 전에 특히 이 확인이 먼저다"
            ),
        }
    return {"state": "current", "behind": 0, "cached": cached_age is not None, "message": f"최신 ({basis})"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="검사할 레포 경로")
    parser.add_argument("--ttl", type=float, default=0, help="이 시간(초) 안에 이미 fetch 했으면 건너뜀")
    args = parser.parse_args(argv)

    result = check(Path(args.root).expanduser().resolve(), ttl_seconds=args.ttl)
    label = {"stale": "FAIL", "current": "PASS", "unknown": "WARN", "not_a_repo": "SKIP"}[result["state"]]
    print(f"{label} checkout freshness: {result['message']}")
    return 1 if result["state"] == "stale" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
