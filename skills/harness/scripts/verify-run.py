#!/usr/bin/env python3
"""verify-run.py — /harness workflow-B 실행 게이트 (결정론적 judge).

사용: python verify-run.py outputs/2026Q1/vat-quarterly-20260609/run.json
exit 0 = PASS, 1 = FAIL(위반), 3 = BLOCKED(정당한 대기·입력 필요), 2 = 사용법 오류.

self-judgment(A=A) 회피: "완료"를 Claude 느낌이 아니라 tool-calls.jsonl 의
증거로만 판정한다. product 의 `npm test`(AC=실행커맨드)에 대응하는,
workflow-B 의 evidence-as-gate. 레포 루트에서 실행 (config/sources.md 기준).

채널(네이티브 MCP vs WebSearch fallback)은 tool-calls 의 구조화 필드
`channel`("mcp"|"websearch"|"webfetch"|...) 로 기록한다. `tool` 은 권위명
(국가법령정보센터 등) 유지 — 게이트 ③ 카탈로그 매칭용. run.json 에
`require_native_authority: true` 면 권위 증거가 mcp 채널이 아닐 때 FAIL.
"""
import json
import pathlib
import sys

USAGE = """usage: python verify-run.py <run.json 경로>

exit 0 = PASS, 1 = FAIL(위반), 3 = BLOCKED(정당한 대기·입력 필요), 2 = 사용법 오류.
"""

# Windows 기본 stdout(cp949)은 ✅❌— 를 못 찍고 크래시 → utf-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        print(USAGE.rstrip())
        return 0

    if len(sys.argv) != 2:
        print(USAGE.rstrip())
        return 2

    run_path = pathlib.Path(sys.argv[1])
    if not run_path.exists():
        print(f"❌ run.json 없음: {run_path}")
        return 2

    run = json.loads(run_path.read_text(encoding="utf-8"))
    calls_path = run_path.parent / "tool-calls.jsonl"
    calls = (
        [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if calls_path.exists()
        else []
    )
    sources_path = pathlib.Path("config/sources.md")
    sources = sources_path.read_text(encoding="utf-8") if sources_path.exists() else ""

    require_native = bool(run.get("require_native_authority"))

    # checklist_id → 그 항목에 달린 호출들의 채널 목록
    channels_by_cid: dict = {}
    for c in calls:
        cid = c.get("checklist_id")
        channels_by_cid.setdefault(cid, []).append(c.get("channel") or "unknown")
    called_ids = set(channels_by_cid)

    bad = []
    blocked = []
    incomplete = []

    for item in run.get("checklist", []):
        cid = item.get("id", "?")
        status = item.get("status")

        # blocked = 정당한 대기. generic 미완료와 분리. 사유 필수.
        if status == "blocked":
            reason = item.get("blocked_reason")
            if not reason:
                bad.append(f"[{cid}] blocked 인데 blocked_reason 없음 — 사유 없는 차단 금지")
            else:
                blocked.append(f"[{cid}] {reason}")
            continue

        # error = 경성 실패. pending/in_progress = 미도달(블록 시 용인).
        if status == "error":
            bad.append(f"[{cid}] error 상태 — 복구 후 재실행")
            continue
        if status != "completed":
            incomplete.append(f"[{cid}] 미완료 (status={status})")
            continue

        # ② 권위 필요 항목엔 증거 필수 (추정 작성 차단)
        if item.get("requires_authority"):
            if cid not in called_ids:
                bad.append(f"[{cid}] requires_authority 인데 tool-calls 증거 없음 — 추정 작성 금지")
            # ⑤ 네이티브 권위 강제 (선택) — 증거가 mcp 채널이 아니면 FAIL
            elif require_native:
                non_mcp = sorted({ch for ch in channels_by_cid[cid] if ch != "mcp"})
                if non_mcp:
                    bad.append(
                        f"[{cid}] require_native_authority 인데 비-mcp 채널 {non_mcp} "
                        "— 1순위 MCP 직접 호출 경로 아님"
                    )

    # ③ 호출 도구가 config/sources.md 카탈로그에 실존 (환각 도구 차단)
    for c in calls:
        base = c.get("tool", "").split("/")[0].split(".")[0]
        if base and sources and base not in sources:
            bad.append(f"[{c.get('checklist_id')}] 미등록 도구 '{c.get('tool')}' (config/sources.md 에 없음)")

    # 채널 분포 (가시화) — 전체 호출 기준
    tally: dict = {}
    for c in calls:
        ch = c.get("channel") or "unknown"
        tally[ch] = tally.get(ch, 0) + 1
    tally_str = " ".join(f"{k}:{v}" for k, v in sorted(tally.items())) or "없음"

    # 우선순위: 경성위반(bad) > 블록 > 미완료(incomplete) > PASS.
    # 블록이 있으면 pending 다운스트림은 "블록으로 미도달"이라 FAIL 이 아니다
    # (run.json 은 전 항목 pending 으로 깔고 시작 → early block 이 FAIL 로 가려지던 갭-3 수정).
    if bad:
        print(f"❌ FAIL ({len(bad)}건):")
        for b in bad:
            print("  -", b)
        return 1

    if blocked:
        print(f"⏸ BLOCKED ({len(blocked)}건 — 사유 해결 후 재실행, '완료' 아님):")
        for b in blocked:
            print("  -", b)
        if incomplete:
            print(f"   (다운스트림 {len(incomplete)}항목 미도달 — 블록으로 중단)")
        print(f"   권위 증거 {len(calls)}건 [채널 {tally_str}]")
        return 3

    if incomplete:
        print(f"❌ FAIL ({len(incomplete)}건 미완료 — 블록도 아님, 완료 주장 불가):")
        for b in incomplete:
            print("  -", b)
        return 1

    n = len(run.get("checklist", []))
    native_note = " (네이티브 강제)" if require_native else ""
    print(f"✅ PASS — {n}항목 완료, 권위 증거 {len(calls)}건 [채널 {tally_str}]{native_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
