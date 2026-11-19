#!/usr/bin/env python3
"""세션 초점(focus) — "이 세션의 하네스 루트는 어디인가"를 세션별 상태 파일로 선언한다.

왜 (h-e M32 2026-09-05 D10): 하네스 훅 4개는 세션 cwd 만 보고, 스킬 문서는 `--root .` 였다.
cwd 와 다른 레포의 하네스를 한 세션이 운용하면 훅 표시·HANDOFF 기록처가 엉뚱한 레포를 가리켰다.
초점 파일 하나로 훅·스킬이 cwd 대신 소유 레포를 본다.

파일: `<HOME>/.claude/state/harness-focus/<session>.json` — `{root, work_id, set_at}`.
  HOME 은 `HARNESS_USER_HOME` 이 있으면 그것(테스트 밀폐 — agent_model_guard 와 같은 관례).
  세션 키는 `--session` → `CLAUDE_CODE_SESSION_ID` → `CODEX_SESSION_ID` 순. 값이 `<runtime>:<uuid>`(claude:·codex: …)면
  접두어를 벗겨 bare uuid 를 키로 쓴다 — 훅 payload 의 `session_id` 가 bare 라서 같은 파일을 봐야 한다(h-e M33).
레포 안 파일이 아닌 이유: cwd 레포를 더럽히지 않고 세션 간 누수가 없다(statusline-ctx 선례).

폴백(resolve): 초점이 없거나 세션이 다르거나 root 가 실재하지 않거나 하네스 레포가 아니면 cwd.
  resolve 는 항상 exit 0 · stdout 1줄 · POSIX 슬래시 — Git Bash `$(…)` 가 그대로 `--root` 에 넣는다.

사용:
  harness_focus.py set --root <path> [--work-id ID] [--session S]
  harness_focus.py resolve [--session S] [--cwd P]
  harness_focus.py show [--session S]
  harness_focus.py clear [--session S]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_SUBDIR = Path(".claude") / "state" / "harness-focus"


def user_home() -> Path:
    return Path(os.environ.get("HARNESS_USER_HOME") or Path.home())


def session_key(explicit: str | None = None) -> str | None:
    # M33 step-2 (2026-09-05 실측): Codex 셸(PowerShell/네이티브 도구)은 CODEX_SESSION_ID 를 준다 —
    # 훅 payload session_id 와 같은 값. bash 도구 경로는 비므로 그때는 --session 으로 명시한다.
    raw = explicit or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CODEX_SESSION_ID") or ""
    raw = raw.strip()
    if not raw:
        return None
    # 훅 payload 의 session_id 는 bare uuid, work_state 토큰은 <runtime>:<uuid>(claude:·codex:) —
    # 둘을 같은 키로. M32 는 claude: 만 벗겨 codex:<uuid> 가 codex_<uuid>.json 으로 갈라졌다(M33 step-1).
    head, sep, tail = raw.partition(":")
    if sep and head.isalnum() and tail.strip():
        raw = tail.strip()
    # 파일명 안전화 — 그 밖의 ':' 는 치환
    return raw.replace(":", "_").replace("/", "_").replace("\\", "_")


def focus_path(session: str) -> Path:
    return user_home() / STATE_SUBDIR / f"{session}.json"


def posix(p: Path) -> str:
    return p.resolve().as_posix()


def is_harness_repo(root: Path) -> bool:
    """하네스 레포 판정 — 훅 `find_harness_root` 와 같은 기준."""
    if (root / ".harness" / "work.json").is_file():
        return True
    roadmap = root / "ROADMAP.md"
    if roadmap.is_file():
        try:
            return "harness:goal" in roadmap.read_text(encoding="utf-8", errors="replace")[:8000]
        except OSError:
            return False
    return False


def read_focus(session: str | None) -> dict | None:
    if session is None:
        return None
    path = focus_path(session)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_root(session: str | None, cwd: Path) -> Path:
    """초점 root 또는 cwd. 폴백 조건은 모듈 docstring."""
    data = read_focus(session)
    if not data:
        return cwd
    raw = data.get("root")
    if not isinstance(raw, str) or not raw.strip():
        return cwd
    root = Path(raw)
    if not root.is_dir() or not is_harness_repo(root):
        return cwd
    return root


def cmd_set(args: argparse.Namespace) -> int:
    session = session_key(args.session)
    if session is None:
        print("focus: FAIL — 세션 키 없음 (CLAUDE_CODE_SESSION_ID·CODEX_SESSION_ID 또는 --session)", file=sys.stderr)
        return 2
    root = Path(args.root)
    if not root.is_dir():
        print(f"focus: FAIL — root 가 디렉터리가 아님: {root}", file=sys.stderr)
        return 2
    if not is_harness_repo(root):
        print(f"focus: FAIL — 하네스 레포가 아님(.harness/work.json·ROADMAP harness:goal 없음): {root}", file=sys.stderr)
        return 2
    path = focus_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": posix(root),
        "work_id": args.work_id,
        "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"focus: {payload['root']}" + (f" (work={args.work_id})" if args.work_id else ""))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    print(posix(resolve_root(session_key(args.session), cwd)))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    session = session_key(args.session)
    data = read_focus(session)
    if not data:
        print("focus: (없음)")
        return 0
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    session = session_key(args.session)
    if session is None:
        print("focus: (세션 키 없음 — 지울 것 없음)")
        return 0
    path = focus_path(session)
    if path.is_file():
        path.unlink()
        print("focus: cleared")
    else:
        print("focus: (없음)")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="세션 초점 — 하네스 루트 선언")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_set = sub.add_parser("set")
    p_set.add_argument("--root", required=True)
    p_set.add_argument("--work-id", default=None)
    p_set.add_argument("--session", default=None)
    p_set.set_defaults(func=cmd_set)
    p_res = sub.add_parser("resolve")
    p_res.add_argument("--session", default=None)
    p_res.add_argument("--cwd", default=None)
    p_res.set_defaults(func=cmd_resolve)
    p_show = sub.add_parser("show")
    p_show.add_argument("--session", default=None)
    p_show.set_defaults(func=cmd_show)
    p_clr = sub.add_parser("clear")
    p_clr.add_argument("--session", default=None)
    p_clr.set_defaults(func=cmd_clear)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
