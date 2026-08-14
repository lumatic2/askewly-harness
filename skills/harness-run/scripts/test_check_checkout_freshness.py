"""§A-0 게이트 회귀 (2026-07-21 MM1 step-3).

실제 git 저장소로 검증한다 — 낙오는 "원격에 커밋이 있는데 로컬이 모르는 상태"라
모킹으로는 재현되지 않는다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_checkout_freshness as gate


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    origin, seed, clone = tmp_path / "o.git", tmp_path / "seed", tmp_path / "clone"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True)
    _git(seed, "config", "user.email", "t@e.com")
    _git(seed, "config", "user.name", "t")
    (seed / "a.txt").write_text("1\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
    return seed, clone


def _advance(seed: Path, n: int) -> None:
    for i in range(n):
        (seed / f"b{i}.txt").write_text("x\n", encoding="utf-8")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-m", f"c{i}")
    _git(seed, "push", "-q", "origin", "main")


def test_stale_checkout_fails_the_gate(tmp_path: Path) -> None:
    # 2026-07-20 사고 재현: 원격이 앞서 있으면 게이트가 막는다.
    seed, clone = _pair(tmp_path)
    _advance(seed, 4)

    result = gate.check(clone)

    assert result["state"] == "stale" and result["behind"] == 4, result
    assert gate.main(["--root", str(clone)]) == 1


def test_current_checkout_passes(tmp_path: Path) -> None:
    # 최신이면 통과 — 작업을 못 하게 막지 않는다.
    _seed, clone = _pair(tmp_path)

    assert gate.check(clone)["state"] == "current"
    assert gate.main(["--root", str(clone)]) == 0


def test_unreachable_remote_is_unknown_not_current(tmp_path: Path) -> None:
    # 실패 probe: fetch 실패를 최신으로 오판하지 않는다. 단 작업은 막지 않는다.
    seed, clone = _pair(tmp_path)
    _advance(seed, 2)
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    result = gate.check(clone)

    assert result["state"] == "unknown", result
    assert "확인 불가" in result["message"]
    assert gate.main(["--root", str(clone)]) == 0


def test_non_repo_is_skipped(tmp_path: Path) -> None:
    # 레포가 아니면 조용히 건너뛴다(게이트가 엉뚱한 곳에서 울지 않게).
    assert gate.check(tmp_path)["state"] == "not_a_repo"


def test_gate_does_not_move_the_working_tree(tmp_path: Path) -> None:
    # 원격 ref 갱신만 — merge/rebase 금지.
    seed, clone = _pair(tmp_path)
    _advance(seed, 2)
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True, text=True, check=True).stdout

    gate.check(clone)

    after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True, text=True, check=True).stdout
    assert before == after


def test_cache_is_labelled_as_cache_not_verification(tmp_path: Path) -> None:
    # 2026-07-21 독립 검증 적발: --ttl 창 안에서 원격이 앞서가면 못 잡는다.
    # 한계는 감수하되 캐시를 "검증됨"이라 말하지 않는다 — 문구가 사각지대를 숨기면 안 된다.
    seed, clone = _pair(tmp_path)
    gate.check(clone)  # 캐시 성립
    _advance(seed, 3)

    result = gate.check(clone, ttl_seconds=3600)

    assert result["cached"] is True, result
    assert "캐시" in result["message"], result


def test_ttl_zero_catches_what_the_cache_hid(tmp_path: Path) -> None:
    # 창을 끄면 반드시 잡는다 — 중요한 판단 전 재확인 경로.
    seed, clone = _pair(tmp_path)
    gate.check(clone)
    _advance(seed, 3)

    result = gate.check(clone, ttl_seconds=0)

    assert result["state"] == "stale" and result["behind"] == 3, result
    assert result["cached"] is False
