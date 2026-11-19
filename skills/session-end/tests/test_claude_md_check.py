"""claude_md_check 회귀 — 삭제·이동된 경로를 CLAUDE.md 백틱 경로와 대조한다."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import claude_md_check as cmc  # noqa: E402


def g(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def make(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("실행은 `scripts/run.py`, 설정은 `docs/setup.md`, 단어 `ruff`.\n", encoding="utf-8")
    (root / "scripts" / "run.py").write_text("x = 1\n", encoding="utf-8")
    (root / "scripts" / "other.py").write_text("y = 1\n", encoding="utf-8")
    (root / "HANDOFF.md").write_text("# h\n", encoding="utf-8")
    g(root, "init", "-q")
    g(root, "add", "-A")
    g(root, "commit", "-qm", "base")
    return root


def test_nothing_touched(tmp_path):
    root = make(tmp_path)
    g(root, "rm", "-q", "scripts/other.py")
    g(root, "commit", "-qm", "rm other")
    out = cmc.check(root)
    assert out[0].startswith("CLAUDE.md 점검: 닿는 것 없음 (삭제·이동 1건")


def test_deleted_and_moved_paths_are_reported(tmp_path):
    root = make(tmp_path)
    (root / "tools").mkdir()
    g(root, "mv", "scripts/run.py", "tools/run.py")
    g(root, "commit", "-qm", "mv")
    out = "\n".join(cmc.check(root))
    assert "`scripts/run.py`" in out and "tools/run.py 로 옮겨졌다" in out
    g(root, "rm", "-q", "tools/run.py")
    g(root, "commit", "-qm", "rm")
    assert "삭제됐다" in "\n".join(cmc.check(root))


def test_new_files_line_and_no_history(tmp_path):
    root = make(tmp_path)
    (root / "scripts" / "new_tool.py").write_text("z = 1\n", encoding="utf-8")
    g(root, "add", "-A")
    g(root, "commit", "-qm", "add")
    assert "새 파일 1개(스크립트 1개)" in "\n".join(cmc.check(root))
    bare = tmp_path / "b"
    bare.mkdir()
    (bare / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    assert "기준 커밋 없음" in cmc.check(bare)[0]


def test_bare_filename_does_not_match_nested_files():
    assert not cmc.touches("SKILL.md", "deprecated/book/SKILL.md")
    assert cmc.touches("SKILL.md", "SKILL.md")
    assert cmc.touches("scripts/run.py", "a/scripts/run.py") and cmc.touches("docs", "docs/x.md") is False
