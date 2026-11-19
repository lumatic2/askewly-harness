import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "retire_check.py"
OLD = "old-cmd-xyz"


def make_repo(root, name, files):
    repo = root / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for rel, text in files.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)


def run(root, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), OLD, "--root", str(root), *extra],
                          capture_output=True, encoding="utf-8")


def test_live_file_found(tmp_path):
    make_repo(tmp_path, "a", {"src/x.py": f"call {OLD}\n"})
    make_repo(tmp_path, "b", {"README.md": "clean\n"})
    r = run(tmp_path)
    assert r.returncode == 1
    assert "잔존 1건 · 1레포" in r.stdout


def test_history_only_is_zero(tmp_path):
    make_repo(tmp_path, "a", {"changesets/c.md": f"{OLD}\n", "HANDOFF.md": OLD})
    make_repo(tmp_path, "b", {"x.txt": "clean\n"})
    r = run(tmp_path)
    assert r.returncode == 0
    assert "잔존 0 — 은퇴 완료" in r.stdout


def test_include_history(tmp_path):
    make_repo(tmp_path, "a", {"changesets/c.md": f"{OLD}\n"})
    make_repo(tmp_path, "b", {"x.txt": "clean\n"})
    r = run(tmp_path, "--include-history")
    assert r.returncode == 1
    assert "잔존 1건" in r.stdout
