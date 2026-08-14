#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append one session entry to $HARNESS_JOURNAL_DIR/YYYY-MM-DD.md.

This helper intentionally does one thing: append a dated session block to the
daily vault log and print the exact content that was written. It does not read
or modify repository files.
"""
import os
import io
import os
import platform
import os
import subprocess
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _host_label(prefix):
    """미등재 환경을 `prefix(hostname)` 로 **보이게** 만든다 — 조용한 오기록 금지."""
    try:
        h = subprocess.run(["hostname"], capture_output=True, text=True,
                           check=False).stdout.split(".", 1)[0]
    except Exception:
        h = ""
    safe = "".join(c for c in h if c.isalnum() or c in "-_") or "unknown"
    return f"{prefix}({safe})"


def _mac_label(hostname):
    """hostname → 기기 라벨. 미등재 기기는 **조용히 오기록되지 않게** 호스트명을 보여준다.

    hostname 을 라벨로 매핑하고, 미등재 기기는 호스트명을 그대로 보여준다.
    """
    h = (hostname or "").split(".", 1)[0]
    for needle, label in (("MacBookAir", "Mac Air"),
                          ("MacBookPro", "MacBook Pro"),
                          ("Macmini", "Mac mini")):
        if needle.lower() in h.lower():
            return label
    safe = "".join(c for c in h if c.isalnum() or c in "-_") or "unknown"
    return f"Mac({safe})"


def device_label():
    """Return a short device label while avoiding hostname encoding issues."""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        try:
            hostname = subprocess.run(
                ["hostname"], capture_output=True, text=True, check=False
            ).stdout
        except Exception:
            hostname = ""
        return _mac_label(hostname)

    try:
        version = Path("/proc/version").read_text(errors="replace").lower()
    except Exception:
        version = ""
    if "microsoft" in version:
        return "Windows"
    return _host_label("Linux")


def main():
    body = sys.stdin.read().strip("\n")
    if not body:
        print("본문이 비었습니다 (stdin 없음) - 기록하지 않음", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    label = device_label()

    log = Path(os.environ.get("HARNESS_JOURNAL_DIR", str(Path.home() / "harness-journal"))) / f"{today}.md"
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
