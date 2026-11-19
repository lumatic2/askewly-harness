"""skills/ 가 플러그인 설치 위치를 고정 경로로 못 박지 않는지, 치환이 실제로 들어갔는지 검사한다."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync  # noqa: E402

SKILLS = ROOT / "skills"
SKILL_NAMES = ("harness-plan", "harness-run", "harness-done", "harness-bootstrap", "session-end")
# 폴더 복사 설치 시절의 고정 경로(슬래시·역슬래시 둘 다) — 쪼개 적어 이 파일 자신이 걸리지 않게 한다.
FIXED = re.compile(r"\.(?:claude|codex)" + r"[/\\]+skills")


def fixed_path_hits(skills_dir: Path) -> list[str]:
    hits = []
    for p in sorted(skills_dir.rglob("*")):
        if not p.is_file():
            continue
        data = p.read_bytes()
        if b"\0" in data[:4096]:  # 바이너리는 건너뛴다 — 확장자로 거르지 않는다
            continue
        for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if FIXED.search(line):
                hits.append(f"{p.relative_to(skills_dir).as_posix()}:{i}: {line.strip()[:90]}")
    return hits


def test_no_fixed_install_paths():
    assert all((SKILLS / n / "SKILL.md").is_file() for n in SKILL_NAMES), "skills/ 가 비었거나 스킬이 빠졌다"
    hits = fixed_path_hits(SKILLS)
    assert not hits, "고정 설치 경로 잔류:\n" + "\n".join(hits)


def test_fixed_path_scan_catches_backslash_and_extensionless(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "run").write_text("cd ~\\.claude" + "\\skills\\x\n", encoding="utf-8")
    assert fixed_path_hits(tmp_path)


def test_plugin_root_resolution_landed():
    """치환이 실제로 들어갔는가 — 다섯 스킬 본문이 플러그인 루트 조각으로 스크립트를 찾는다."""
    for n in SKILL_NAMES:
        body = (SKILLS / n / "SKILL.md").read_text(encoding="utf-8")
        assert sync.PLUGIN_ROOT_LINE in body, f"{n}: 플러그인 루트 해석 조각이 없다"
    assert "sort -V" in sync.PLUGIN_ROOT_LINE and "못 찾았다" in sync.PLUGIN_ROOT_LINE
    done = (SKILLS / "harness-done" / "SKILL.md").read_text(encoding="utf-8")
    assert '"$HARNESS_SCRIPTS/../../harness-done/bin/retire_check.py"' in done


def test_codex_display_names_use_plugin_prefix():
    yamls = sorted(SKILLS.glob("*/agents/openai.yaml"))
    assert yamls, "Codex 표시 파일이 없다"
    for y in yamls:
        text = y.read_text(encoding="utf-8")
        assert f"$askewly:{y.parent.parent.name}" in text, y
        assert not re.search(r"\$(?:harness-|session-end)", text), y


def test_skill_name_rewrite_respects_boundary():
    pat, repl = sync.OPENAI_YAML_P
    assert re.sub(pat, repl, "Use $harness-plan now.") == "Use $askewly:harness-plan now."
    assert re.sub(pat, repl, "$harness-plan-notes") == "$harness-plan-notes"


def test_leak_check_catches_fixed_path():
    """Failure probe — 고정 경로 한 줄이 든 트리는 leak-check 가 잡아야 한다."""
    line = 'HARNESS_SCRIPTS="$HOME/.claude' + '/skills/harness-run/scripts"\n'
    assert sync.leak_check({"skills/harness-plan/SKILL.md": line.encode("utf-8")})


def test_leak_check_allows_only_this_public_repo():
    acct = "luma" + "tic2"
    ok = [
        f'"homepage": "https://github.com/{acct}/askewly-harness",',
        f'"url": "https://github.com/{acct}"',
        f"/plugin marketplace add {acct}/askewly-harness",
    ]
    bad = [
        f"https://github.com/{acct}/private-repo",
        f"https://github.com/{acct}/askewly-harness-internal",
        f"/Users/{acct}/work",
    ]
    for line in ok:
        assert not sync.leak_check({"x.md": line.encode("utf-8")}), line
    for line in bad:
        assert sync.leak_check({"x.md": line.encode("utf-8")}), line


def test_repo_scan_skips_ignored_files(tmp_path):
    """leak-check-only 는 제품에 들어가는 파일만 본다 — gitignored 파일은 보지 않고 미추적 파일은 본다."""

    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / ".gitignore").write_text("/plans/\n", encoding="utf-8")
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p.md").write_text("ignored", encoding="utf-8")
    (tmp_path / "skills" / "plans").mkdir(parents=True)
    (tmp_path / "skills" / "plans" / "t.md").write_text("shipped", encoding="utf-8")
    (tmp_path / "new.md").write_text("untracked", encoding="utf-8")
    tree = sync.scan_repo_tree(tmp_path)
    assert "new.md" in tree and "skills/plans/t.md" in tree
    assert "plans/p.md" not in tree


def test_repo_gitignore_is_root_anchored():
    """운영 파일 무시 규칙은 루트에만 걸린다 — skills/ 안의 같은 이름 폴더를 삼키지 않는다."""
    lines = [l.strip() for l in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
    for name in ("plans/", "changesets/", "archive/", "tmp/", "research/"):
        assert f"/{name}" in lines and name not in lines, name
