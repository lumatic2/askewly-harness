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
    data = collect(root)
    names = [
        data["claude_plugin"]["name"],
        data["codex_plugin"]["name"],
        data["claude_market"]["plugins"][0]["name"],
        data["codex_market"]["plugins"][0]["name"],
    ]
    assert names == ["askewly"] * 4, f"names: {names}"

    versions = [data["claude_plugin"]["version"], data["codex_plugin"]["version"]]
    for key in ("claude_market", "codex_market"):
        entry = data[key]["plugins"][0]
        if "version" in entry:
            versions.append(entry["version"])
    assert len(set(versions)) == 1, f"version mismatch: {versions}"


def test_names_and_versions_agree():
    check(ROOT)


def test_version_mismatch_is_caught(tmp_path):
    for rel in FILES.values():
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    p = tmp_path / FILES["codex_plugin"]
    d = json.loads(p.read_text(encoding="utf-8"))
    d["version"] = "9.9.9"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(AssertionError):
        check(tmp_path)
