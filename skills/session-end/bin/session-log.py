#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session-end vault logger.

세션 엔트리를 오늘 날짜 40-Logs 파일에 append 한다. 판단이 필요 없는 기계적인
부분(기기 레이블 / 날짜 / 파일명 / 헤더 생성 / append)을 전부 처리하고, 본문은
stdin 으로 받는다. 마지막에 기록한 엔트리를 그대로 출력해 STEP 3 출력이 실제
기록물과 100% 일치하게 한다(모델 재타이핑 drift 방지).

사용:
    python3 session-log.py <<'BODY'
    한 일
      ...
    BODY
"""
import sys, io, os, platform
from datetime import datetime
from pathlib import Path

sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def device_label():
    """Windows / macOS / WSL / Linux. hostname cp949 깨짐을 피해 OS 판정만 한다."""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        return "macOS"
    try:
        ver = Path("/proc/version").read_text(errors="replace").lower()
    except Exception:
        ver = ""
    return "WSL" if "microsoft" in ver else "Linux"


def main():
    body = sys.stdin.read().strip("\n")
    if not body:
        print("본문이 비었습니다 (stdin 없음) — 기록하지 않음", file=sys.stderr)
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
    with log.open("a", encoding="utf-8") as f:
        f.write(entry)

    # 기록한 엔트리를 그대로 relay (STEP 3 출력 = 실제 기록물)
    print(f"── 기록한 세션 {label} · {today} {hhmm} ──\n")
    print(body)
    print(f"\n✓ {log} 기록 완료 (append)")


if __name__ == "__main__":
    main()
