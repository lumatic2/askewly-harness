"""h-e M33 step-5 (F8) — roadmap_hygiene 가 harness-run 경로를 고정하지 않는다."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roadmap_hygiene as rh  # noqa: E402


def _layout(tmp: Path, name: str) -> Path:
    d = tmp / "skills" / name / "scripts"
    d.mkdir(parents=True)
    (d / "roadmap_sync.py").write_text("# stub", encoding="utf-8")
    return d


def _here(tmp: Path) -> Path:
    here = tmp / "skills" / "session-end" / "bin" / "roadmap_hygiene.py"
    here.parent.mkdir(parents=True, exist_ok=True)
    here.write_text("", encoding="utf-8")
    return here


def test_env_wins(tmp_path: Path) -> None:
    env_dir = _layout(tmp_path / "e", "x")
    _layout(tmp_path, "harness-run")
    assert rh.find_sync_scripts(_here(tmp_path), {"HARNESS_SCRIPTS": str(env_dir)}) == env_dir


def test_sibling_harness_run(tmp_path: Path) -> None:
    d = _layout(tmp_path, "harness-run")
    assert rh.find_sync_scripts(_here(tmp_path), {}) == d


def test_staging_alias_layout(tmp_path: Path) -> None:
    d = _layout(tmp_path, "harness-run-stg")
    assert rh.find_sync_scripts(_here(tmp_path), {}) == d


def test_none_found_warns_not_silent(tmp_path: Path, capsys) -> None:
    got = rh.find_sync_scripts(_here(tmp_path), {})
    assert got == tmp_path / "skills" / "harness-run" / "scripts"
    assert "roadmap_sync.py 를 못 찾음" in capsys.readouterr().err
