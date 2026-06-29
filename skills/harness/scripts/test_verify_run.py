#!/usr/bin/env python3
"""test_verify_run.py — verify-run.py 게이트의 계약을 박제하는 회귀 테스트.

하네스 자체도 TDD로 보호한다(정의 v1.0 차별점 #4). config/sources.md 없는
임시 디렉터리에서 돌려 ③ 카탈로그 매칭은 비활성, ①②④⑤·blocked 만 격리 검증.

실행: python test_verify_run.py   (exit 0 = 전 케이스 통과)
"""
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
VERIFY = HERE / "verify-run.py"


def run_case(run_obj, calls):
    """임시 디렉터리에 run.json + tool-calls.jsonl 쓰고 verify-run.py 실행 → exit code."""
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        (dp / "run.json").write_text(json.dumps(run_obj, ensure_ascii=False), encoding="utf-8")
        if calls is not None:
            lines = "\n".join(json.dumps(c, ensure_ascii=False) for c in calls)
            (dp / "tool-calls.jsonl").write_text(lines, encoding="utf-8")
        # cwd=dp → config/sources.md 없음 → ③ 비활성 (격리)
        # Windows: 자식 stdout 에 ✅❌ → 부모 캡처도 utf-8 강제 (cp949 디코드 크래시 방지)
        r = subprocess.run([sys.executable, str(VERIFY), str(dp / "run.json")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=dp)
        return r.returncode, r.stdout


def item(cid, *, status="completed", auth=False, reason=None):
    it = {"id": cid, "item": cid, "requires_authority": auth, "status": status}
    if reason is not None:
        it["blocked_reason"] = reason
    return it


def call(cid, channel=None, tool="국가법령정보센터"):
    c = {"checklist_id": cid, "tool": tool, "result_digest": "x", "ts": "t"}
    if channel is not None:
        c["channel"] = channel
    return c


CASES = [
    # name, run, calls, expected_exit
    ("T1 회귀 PASS (completed + mcp 증거, 플래그 없음)",
     {"checklist": [item("c1"), item("c2", auth=True)]},
     [call("c2", "mcp")], 0),

    ("T2 native 강제 + web 증거 → FAIL",
     {"require_native_authority": True, "checklist": [item("c2", auth=True)]},
     [call("c2", "websearch")], 1),

    ("T3 native 강제 + mcp 증거 → PASS",
     {"require_native_authority": True, "checklist": [item("c2", auth=True)]},
     [call("c2", "mcp")], 0),

    ("T4 플래그 없음 + web 증거 → PASS (fallback 허용)",
     {"checklist": [item("c2", auth=True)]},
     [call("c2", "websearch")], 0),

    ("T5 blocked + 사유 → exit 3 BLOCKED",
     {"checklist": [item("c1"), item("c2", status="blocked", reason="law-mcp off·인증 누락")]},
     [], 3),

    ("T6 blocked 무사유 → FAIL",
     {"checklist": [item("c2", status="blocked")]},
     [], 1),

    ("T7 구식 레코드(channel 없음) + 플래그 없음 → PASS (하위호환)",
     {"checklist": [item("c2", auth=True)]},
     [call("c2")], 0),

    ("T8 native 강제 + 구식(channel 없음=unknown) → FAIL (안전측)",
     {"require_native_authority": True, "checklist": [item("c2", auth=True)]},
     [call("c2")], 1),

    ("T9 requires_authority 증거 없음 → FAIL",
     {"checklist": [item("c2", auth=True)]},
     [], 1),

    # 갭-3: early block + pending 다운스트림 (run.json 은 전 항목 pending 으로 시작)
    ("T10 blocked + pending 다운스트림 → exit 3 (FAIL 로 가리지 않음)",
     {"checklist": [item("c1"), item("c2", status="blocked", reason="law-mcp off"),
                    item("c3", status="pending"), item("c4", status="pending")]},
     [], 3),

    ("T11 pending 만 (blocked 없음) → FAIL (완료 주장 불가)",
     {"checklist": [item("c1"), item("c2", status="pending")]},
     [], 1),

    ("T12 error 상태 → FAIL (경성 실패)",
     {"checklist": [item("c2", status="error")]},
     [], 1),
]


def main():
    fails = 0
    help_result = subprocess.run([sys.executable, str(VERIFY), "--help"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    if help_result.returncode == 0 and "usage: python verify-run.py" in help_result.stdout:
        print("✅ T0 --help → usage + exit 0")
    else:
        fails += 1
        print(f"❌ T0 --help → exit {help_result.returncode}, stdout={help_result.stdout!r}")

    for name, run_obj, calls, expected in CASES:
        code, out = run_case(run_obj, calls)
        ok = code == expected
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}  (exit {code}, 기대 {expected})")
        if not ok:
            fails += 1
            print("    ↳", out.strip().replace("\n", " | "))
    print(f"\n{'전부 통과' if not fails else str(fails) + '건 실패'} ({len(CASES) + 1} 케이스)")
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
