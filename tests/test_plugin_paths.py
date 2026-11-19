"""skills/ 가 플러그인 설치 위치를 고정 경로로 못 박지 않는지 검사한다."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync  # noqa: E402

# 폴더 복사 설치 시절의 고정 경로 — 문자열을 쪼개 적어 이 파일 자신이 걸리지 않게 한다.
FIXED = re.compile(r"\.(?:claude|codex)" + "/skills")
TEXT = {".md", ".py", ".sh", ".ps1", ".txt", ".json", ".yaml", ".yml"}


def fixed_path_hits(skills_dir: Path) -> list[str]:
    hits = []
    for p in sorted(skills_dir.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if FIXED.search(line):
                hits.append(f"{p.relative_to(skills_dir).as_posix()}:{i}: {line.strip()[:90]}")
    return hits


def test_no_fixed_install_paths():
    hits = fixed_path_hits(ROOT / "skills")
    assert not hits, "고정 설치 경로 잔류:\n" + "\n".join(hits)


def test_leak_check_catches_fixed_path():
    """Failure probe — 고정 경로 한 줄이 든 트리는 leak-check 가 잡아야 한다."""
    line = 'HARNESS_SCRIPTS="$HOME/.claude' + '/skills/harness-run/scripts"\n'
    hits = sync.leak_check({"skills/harness-plan/SKILL.md": line.encode("utf-8")})
    assert hits, "leak-check 가 고정 설치 경로를 놓쳤다"


def test_leak_check_allows_public_repo_url():
    """공개 레포 주소는 개인 배선이 아니다 — 등록 파일에 들어간다."""
    line = '"homepage": "https://github.com/' + 'lumatic2/askewly-harness"\n'
    assert not sync.leak_check({".claude-plugin/plugin.json": line.encode("utf-8")})


def test_repo_scan_skips_ignored_files():
    """leak-check-only 는 제품에 들어가는 파일만 본다 — gitignored 운영 파일은 보지 않는다."""
    tree = sync.scan_repo_tree()
    assert "README.md" in tree
    assert not any(
        k.startswith((".harness/", "plans/", "research/")) or k in {"CLAUDE.md", "ROADMAP.md"}
        for k in tree
    )
