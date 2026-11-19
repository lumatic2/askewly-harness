#!/usr/bin/env python3
"""세션 초점(harness_focus) 회귀 — set→resolve 왕복·세션 격리·root 부재/비하네스 폴백·clear."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import harness_focus as hf

SCRIPT = Path(hf.__file__).resolve()


def harness_repo(path: Path) -> Path:
    (path / ".harness").mkdir(parents=True, exist_ok=True)
    (path / ".harness" / "work.json").write_text("{}", encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HARNESS_USER_HOME", str(h))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return h


def test_set_then_resolve_roundtrip(home: Path, tmp_path: Path) -> None:
    target = harness_repo(tmp_path / "target")
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    assert hf.main(["set", "--root", str(target), "--session", "s1", "--work-id", "W"]) == 0
    state = json.loads((home / ".claude" / "state" / "harness-focus" / "s1.json").read_text(encoding="utf-8"))
    assert state["root"] == target.resolve().as_posix()
    assert state["work_id"] == "W"
    assert hf.resolve_root("s1", cwd) == Path(state["root"])


def test_resolve_output_is_single_posix_line(home: Path, tmp_path: Path) -> None:
    target = harness_repo(tmp_path / "t")
    hf.main(["set", "--root", str(target), "--session", "s1"])
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "resolve", "--session", "s1", "--cwd", str(tmp_path)],
        capture_output=True, text=True, env={**dict(__import__("os").environ), "HARNESS_USER_HOME": str(home)},
    )
    assert out.returncode == 0
    assert out.stdout.count("\n") == 1
    assert "\\" not in out.stdout
    assert out.stdout.strip() == target.resolve().as_posix()


def test_other_session_focus_does_not_leak(home: Path, tmp_path: Path) -> None:
    target = harness_repo(tmp_path / "t")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    hf.main(["set", "--root", str(target), "--session", "other"])
    assert hf.resolve_root("mine", cwd) == cwd
    assert hf.resolve_root(None, cwd) == cwd


def test_missing_root_falls_back_to_cwd(home: Path, tmp_path: Path) -> None:
    target = harness_repo(tmp_path / "t")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    hf.main(["set", "--root", str(target), "--session", "s1"])
    # 파일의 root 를 존재하지 않는 경로로 바꿔도 훅/resolve 는 죽지 않고 cwd
    p = hf.focus_path("s1")
    data = json.loads(p.read_text(encoding="utf-8"))
    data["root"] = str(tmp_path / "gone")
    p.write_text(json.dumps(data), encoding="utf-8")
    assert hf.resolve_root("s1", cwd) == cwd


def test_non_harness_root_is_rejected_on_set_and_ignored_on_resolve(home: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert hf.main(["set", "--root", str(plain), "--session", "s1"]) == 2
    assert hf.main(["set", "--root", str(tmp_path / "nope"), "--session", "s1"]) == 2
    # 손으로 심어진 비하네스 root 도 resolve 는 무시
    p = hf.focus_path("s1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"root": plain.as_posix()}), encoding="utf-8")
    assert hf.resolve_root("s1", cwd) == cwd


def test_roadmap_goal_marker_counts_as_harness_repo(home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "ROADMAP.md").write_text('<!-- harness:goal id="x" -->\n', encoding="utf-8")
    assert hf.main(["set", "--root", str(repo), "--session", "s1"]) == 0


def test_clear_removes_file_and_is_idempotent(home: Path, tmp_path: Path) -> None:
    target = harness_repo(tmp_path / "t")
    hf.main(["set", "--root", str(target), "--session", "s1"])
    assert hf.focus_path("s1").is_file()
    assert hf.main(["clear", "--session", "s1"]) == 0
    assert not hf.focus_path("s1").is_file()
    assert hf.main(["clear", "--session", "s1"]) == 0


def test_session_key_from_env_and_sanitized(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc-123")
    assert hf.session_key() == "abc-123"
    assert hf.session_key("claude:abc") == "abc"
    assert hf.session_key("codex:abc") == "abc"  # M33 step-1: 런타임 접두어 전부 벗김
    assert hf.session_key("odd:with:colons") == "with_colons"
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    assert hf.session_key() is None


def test_codex_prefixed_set_writes_bare_uuid_file(home: Path, tmp_path: Path) -> None:
    """M33 step-1 — codex:<uuid> 로 set 하면 훅이 읽는 <uuid>.json 이 생긴다 (M32 는 codex_<uuid>.json)."""
    target = harness_repo(tmp_path / "repo")
    assert hf.main(["set", "--root", str(target), "--session", "codex:abc"]) == 0
    state = home / ".claude" / "state" / "harness-focus"
    assert (state / "abc.json").is_file()
    assert not (state / "codex_abc.json").exists()
    assert hf.resolve_root(hf.session_key("abc"), tmp_path).resolve() == target.resolve()


def test_codex_env_is_session_key_fallback(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M33 step-2 — CLAUDE env 가 없으면 CODEX_SESSION_ID 가 키다 (Codex 셸 실측, 훅 payload 와 같은 값)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setenv("CODEX_SESSION_ID", "cdx-1")
    assert hf.session_key() == "cdx-1"
    target = harness_repo(tmp_path / "repo")
    assert hf.main(["set", "--root", str(target)]) == 0
    assert (home / ".claude" / "state" / "harness-focus" / "cdx-1.json").is_file()
    assert hf.resolve_root(hf.session_key(), tmp_path).resolve() == target.resolve()


def test_claude_env_wins_over_codex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cl-1")
    monkeypatch.setenv("CODEX_SESSION_ID", "cdx-1")
    assert hf.session_key() == "cl-1"
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    monkeypatch.delenv("CODEX_SESSION_ID")
    assert hf.session_key() is None
