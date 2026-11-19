#!/usr/bin/env python3
"""레포 CLAUDE.md 가 가리키는 경로가 마지막 HANDOFF 커밋 뒤로 사라지거나 옮겨졌는지 대조한다 (2026-11-13).

session-end §1b 의 첫 질문을 기계로 본다 — 30일 실측에서 마감의 86% 가 「점검했다」고 적었는데
실제로 CLAUDE.md 를 연 것은 50% 였다. 읽기 전용이고 **항상 exit 0** 이다(마감을 막지 않는다).

기준 = HANDOFF.md 를 마지막으로 커밋한 커밋. 그 뒤 HEAD 까지의 삭제·이동(`git diff --diff-filter=DR`)을
CLAUDE.md 의 백틱 경로와 대조하고, 새로 생긴 파일 수도 한 줄로 찍는다(둘째 질문의 재료).

사용: claude_md_check.py --root <repo>
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"`([^`\s]+)`")


def git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=false", *args],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout if out.returncode == 0 else ""


def path_tokens(text: str) -> set[str]:
    """백틱 안의 경로처럼 보이는 것(슬래시나 확장자가 있는 것)."""
    tokens = set()
    for raw in TOKEN_RE.findall(text):
        tok = raw.strip().lstrip("./").rstrip("/").replace("\\", "/")
        if "/" in tok or re.search(r"\.[A-Za-z0-9]{1,5}$", tok):
            tokens.add(tok)
    return tokens


def touches(token: str, path: str) -> bool:
    if "/" not in token:  # `SKILL.md` 같은 맨 파일 이름은 루트의 그 파일만 — 아무 폴더의 같은 이름에 걸리지 않게
        return path == token
    return path == token or path.endswith("/" + token) or path.startswith(token + "/")


def check(root: Path) -> list[str]:
    claude = root / "CLAUDE.md"
    if not claude.is_file():
        return ["CLAUDE.md 점검: 파일 없음"]
    base = git(root, "log", "-1", "--format=%H", "--", "HANDOFF.md").strip()
    if not base:
        return ["CLAUDE.md 점검: 기준 커밋 없음(HANDOFF.md 커밋 이력이 없다) — 대조하지 않음"]
    tokens = path_tokens(claude.read_text(encoding="utf-8", errors="replace"))
    gone: list[tuple[str, str | None]] = []
    for line in git(root, "diff", "--name-status", "--diff-filter=DR", "-M", f"{base}..HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith("R"):
            gone.append((parts[1], parts[2]))
        elif len(parts) >= 2 and parts[0] == "D":
            gone.append((parts[1], None))
    added = [ln for ln in git(root, "diff", "--name-only", "--diff-filter=A", f"{base}..HEAD").splitlines() if ln]
    out = []
    for old, new in gone:
        for tok in sorted(tokens):
            if touches(tok, old):
                out.append(f"CLAUDE.md 점검: `{tok}` 가 가리키는 {old} 가 " + (f"{new} 로 옮겨졌다" if new else "삭제됐다"))
                break
    if not out:
        out.append(f"CLAUDE.md 점검: 닿는 것 없음 (삭제·이동 {len(gone)}건을 백틱 경로 {len(tokens)}개와 대조)")
    if added:
        scripts = [a for a in added if a.endswith((".py", ".sh", ".ps1", ".mjs", ".ts")) and "/test" not in a and not Path(a).name.startswith("test_")]
        out.append(f"CLAUDE.md 점검: 기준 뒤 새 파일 {len(added)}개(스크립트 {len(scripts)}개) — 다음 세션이 코드만 보고 알 수 없는 것만 할 일로")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        for line in check(Path(args.root).resolve()):
            print(line)
    except Exception as exc:  # 마감을 막지 않는다
        print(f"CLAUDE.md 점검: 실패({type(exc).__name__}) — 건너뜀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
