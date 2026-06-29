#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append one session entry to ~/vault/40-Logs/YYYY-MM-DD.md.

This helper intentionally does one thing: append a dated session block to the
daily vault log and print the exact content that was written. It does not read
or modify repository files.
"""
import io
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def device_label():
    """Return a short OS label while avoiding hostname encoding issues."""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        return "macOS"
    try:
        version = Path("/proc/version").read_text(errors="replace").lower()
    except Exception:
        version = ""
    return "WSL" if "microsoft" in version else "Linux"


def main():
    body = sys.stdin.read().strip("\n")
    if not body:
        print("본문이 비었습니다 (stdin 없음) - 기록하지 않음", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    label = device_label()

    base = os.environ.get("HARNESS_JOURNAL_DIR")
    log_dir = Path(base).expanduser() if base else Path.home() / "vault" / "40-Logs"
    log = log_dir / f"{today}.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text(
            f"---\ntype: log\ndate: {today}\nstatus: active\n---\n# {today}\n\n",
            encoding="utf-8",
        )

    entry = f"## 세션 {label} {hhmm}\n\n{body}\n\n---\n"
    with log.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    print(f"── 기록한 세션 {label} · {today} {hhmm} ──\n")
    print(body)
    print(f"\n✓ {log} 기록 완료 (append)")


if __name__ == "__main__":
    main()
