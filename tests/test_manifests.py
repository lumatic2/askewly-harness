"""Plugin manifest consistency checks (stdlib + pytest only)."""
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "claude_plugin": ".claude-plugin/plugin.json",
    "claude_market": ".claude-plugin/marketplace.json",
    "codex_plugin": ".codex-plugin/plugin.json",
    "codex_market": ".agents/plugins/marketplace.json",
}


def collect(root) -> dict:
    root = Path(root)
    return {
        key: json.loads((root / rel).read_text(encoding="utf-8"))
        for key, rel in FILES.items()
    }


def check(root) -> None:
    root = Path(root)
    data = collect(root)

    # 마켓플레이스마다 플러그인 항목은 하나이고, 이름은 네 곳이 전부 같다.
    for key in ("claude_market", "codex_market"):
        assert len(data[key]["plugins"]) == 1, f"{key}: plugins {len(data[key]['plugins'])}"
    names = [
        data["claude_plugin"]["name"],
        data["codex_plugin"]["name"],
        data["claude_market"]["plugins"][0]["name"],
        data["codex_market"]["plugins"][0]["name"],
        data["claude_market"]["name"],
        data["codex_market"]["name"],
    ]
    assert names == ["askewly"] * 6, f"names: {names}"

    versions = [data["claude_plugin"]["version"], data["codex_plugin"]["version"]]
    for key in ("claude_market", "codex_market"):
        entry = data[key]["plugins"][0]
        if "version" in entry:
            versions.append(entry["version"])
    assert len(set(versions)) == 1, f"version mismatch: {versions}"

    # 두 마켓플레이스 모두 레포 루트를 플러그인으로 가리킨다.
    assert data["claude_market"]["plugins"][0]["source"] == "./"
    assert data["codex_market"]["plugins"][0]["source"] == {"source": "local", "path": "./"}

    # Codex 가 읽는 스킬 폴더가 실제로 있고 스킬이 들어 있다.
    skills = (root / data["codex_plugin"]["skills"]).resolve()
    assert skills.is_dir(), f"skills dir missing: {skills}"
    assert list(skills.glob("*/SKILL.md")), f"no SKILL.md under {skills}"


def test_names_and_versions_agree():
    check(ROOT)


def _copy(tmp_path) -> Path:
    for rel in FILES.values():
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    skill = tmp_path / "skills" / "x"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    return tmp_path


def _mutate(root: Path, key: str, fn) -> None:
    p = root / FILES[key]
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d), encoding="utf-8")


def test_copy_is_valid_before_mutation(tmp_path):
    check(_copy(tmp_path))


@pytest.mark.parametrize("key", ["claude_plugin", "codex_plugin"])
def test_version_mismatch_is_caught(tmp_path, key):
    root = _copy(tmp_path)
    _mutate(root, key, lambda d: d.__setitem__("version", "9.9.9"))
    with pytest.raises(AssertionError):
        check(root)


@pytest.mark.parametrize("key", ["claude_plugin", "codex_plugin"])
def test_plugin_name_mismatch_is_caught(tmp_path, key):
    root = _copy(tmp_path)
    _mutate(root, key, lambda d: d.__setitem__("name", "other"))
    with pytest.raises(AssertionError):
        check(root)


@pytest.mark.parametrize("key", ["claude_market", "codex_market"])
def test_marketplace_entry_name_mismatch_is_caught(tmp_path, key):
    root = _copy(tmp_path)
    _mutate(root, key, lambda d: d["plugins"][0].__setitem__("name", "other"))
    with pytest.raises(AssertionError):
        check(root)


def test_wrong_skills_path_is_caught(tmp_path):
    root = _copy(tmp_path)
    _mutate(root, "codex_plugin", lambda d: d.__setitem__("skills", "./nope/"))
    with pytest.raises(AssertionError):
        check(root)
