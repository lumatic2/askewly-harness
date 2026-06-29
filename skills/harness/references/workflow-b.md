> harness 갈래 본문 (lazy-split, F2). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤 §0 에서 이 갈래로 판정됐을 때 읽는다. §A1/§B2-scope/§B3 등 상호참조는 SKILL.md 에 있다.

## ▶ WORKFLOW-B — playbook 실행 (반복★)

### §C-workflow-B. Step 설계

**playbook 자체가 step 정의**. 실행할 playbook 의 *절차* 항목들을 step 으로 풀어내고, 체크리스트를 검증 절차로 사용.

작업 단위: 1 회 실행 인스턴스 (예: `vat-quarterly 2026Q1`).

### §D-workflow-B. 파일 생성

```bash
mkdir -p outputs/<기수>/<task>-<YYYYMMDD>
# 실행 status machine
cat > outputs/<기수>/<task>-<YYYYMMDD>/run.json <<EOF
{
  "playbook": "<task-slug>",
  "instance": "<기수> <YYYYMMDD>",
  "started_at": "<KST ISO>",
  "checklist": [
    { "id": "c1", "item": "입력 자료 확인",     "requires_authority": false, "status": "pending" },
    { "id": "c2", "item": "기준일 유효성 확인", "requires_authority": true,  "status": "pending" }
  ]
}
EOF
```

playbook 의 체크리스트 항목 각각이 `checklist[]` 의 한 행. 필드:
- `id` — 항목 식별자 (tool-calls 와 연결). `requires_authority` — *수치·결론을 생성*하는 step 이면 `true` (외부도구 증거 필수).
- 도구 호출 로그 `outputs/<기수>/<task>-<YYYYMMDD>/tool-calls.jsonl` — 한 줄당:
  ```json
  {"checklist_id":"c2","tool":"국가법령정보센터","channel":"mcp","mcp_tool":"law-mcp","args":{"query":"부가가치세법 제30조"},"result_digest":"세율 100분의 10","ts":"<KST ISO>"}
  ```
  **`tool` = 권위명** (`config/sources.md` 에 카탈로그된 것 — 국가법령정보센터·국세청·DART 등). `WebFetch`/`WebSearch`/`law-mcp` 같은 *fetch 수단*이 아니다. 게이트 ③ 이 카탈로그 매칭을 강제하므로, 수단명을 `tool` 에 넣으면 "미등록 도구"로 FAIL 한다.
  **`channel` = 수단** — `mcp`(네이티브 직접호출) / `websearch` / `webfetch` 중. `channel:"mcp"` 면 `mcp_tool`(예 `law-mcp`)도 함께. 이 필드가 *네이티브 직접호출 vs fallback* 을 게이트에 가시화한다 (권위명만으론 구분 불가했던 갭). 생략 시 `unknown` 취급.
  > 흔한 실수: `"tool":"WebFetch"` → 게이트 ③ FAIL(미등록). 올바름: `"tool":"국가법령정보센터","channel":"webfetch"` — 권위는 `tool`, 수단은 `channel`.

### §E-workflow-B. 실행

> **게이트**: §B2 적용 — 기본 통과(한 줄 통지 후 진입), "계획부터 보여줘" 류 요청 시만 §E 전 정지. (정책 본문은 §B2 단일 출처)

#### ★ E-1. checklist 항목 전이마다 run.json 갱신
**트리거는 시간이 아니라 항목 전이다.** 각 checklist 항목이 `pending → in_progress → completed` 로 바뀌는 *그 시점*에 `run.json` 을 갱신.

#### E-2. Judge 규약 — 외부 권위 호출 + ★결정론적 게이트
- 수치·결론 생성 step(`requires_authority: true`)은 `config/sources.md` 의 공식 도구를 호출하고 결과를 `tool-calls.jsonl` 에 `checklist_id` 와 함께 박제. 호출 안 한 추정은 step 거부.
- **권위 가용성 + fallback (setup 시 확인 — 카탈로그 권위가 in-session 에 안 불릴 수 있다)**: law-mcp 등 MCP off, Open API 키(`LAW_GO_KR_OC`) 미설정, JS 렌더 페이지(law.go.kr 직접 WebFetch 는 본문 못 가져옴) — 순서대로:
  1. MCP/Open API 직접 호출 가능하면 그걸로 (가장 정확).
  2. 안 되면 **WebSearch → 공식 출처(국가법령정보센터·국세청 등) 확인 → `tool` 에 *그 권위명* 으로 로깅** (수단은 WebSearch 라도 권위는 출처). ※ WebSearch 는 US-only — 한국 법령은 약하면 `ncli`(네이버) 병행.
  3. 공식 출처도 못 찾으면 → `blocked`(추정 금지). MCP 토글이 필요하면 `/mcp-toggle` 을 사용자에게 제안.
- **커밋 전 게이트 (self-judgment 회피)**: 
  ```bash
  HARNESS_SCRIPTS="$HOME/.codex/skills/harness/scripts"
  [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness/scripts"
  python "$HARNESS_SCRIPTS/verify-run.py" outputs/<기수>/<task>-<YYYYMMDD>/run.json
  ```
  체크 ① 전 항목 completed ② requires_authority 항목엔 tool-calls 증거 필수 ③ 미등록 도구 차단 ④ 채널 분포 출력(`[채널 mcp:3 …]`) ⑤ run.json 에 `"require_native_authority": true` 면 권위 증거가 `mcp` 채널 아닐 때 FAIL(1순위 직접호출 강제). **exit 0=PASS / 1=FAIL / 3=BLOCKED**. FAIL 이면 커밋 거부 — 위반 항목으로 복귀. *"완료"는 Claude 판정이 아니라 이 스크립트 PASS 로 정의* (product 의 `npm test` 게이트에 대응하는 evidence-as-gate). 계약 회귀: `scripts/test_verify_run.py`.

#### E-3. outputs 저장 형식
```
outputs/<기수>/<task>-<YYYYMMDD>/
├── run.json              # status machine
├── tool-calls.jsonl      # 외부 도구 호출 로그
├── result.<ext>          # 최종 산출물 (xlsx/pdf/md ...)
└── notes.md              # 사람이 추가로 적는 메모 (선택)
```

#### E-4. 인덱스 표 갱신
실행 완료 시 `playbooks/README.md` 의 "마지막 적용 / 적용 횟수" 자동 증가:
```markdown
| 3 | vat-quarterly | VAT 분기 신고 | 2026-05-17 | 4 |
```

#### E-5. blocked 처리
법령 해석 모호·인증 누락·사용자 의사결정 필요 시 즉시 `blocked` + `blocked_reason`(필수 — 없으면 게이트 FAIL) + 멈춤. 게이트는 blocked 를 generic 미완료와 분리해 **exit 3 (BLOCKED)** 로 보고한다 — false-PASS 도 hallucinated-fail 도 아닌 "정당한 대기, 입력 필요". 사유 해결 후 재실행.

#### E-6. commit 단위
1 회 실행 = 1 commit. **E-2 게이트 PASS 후에만:**
```bash
git commit -m "run(vat-quarterly): 2026Q1 (체크리스트 8/8 + 도구 호출 5건)"
```

#### E-7. ROADMAP milestone sync
`verify-run.py` PASS 후 실행 결과가 milestone DoD 를 만족하면 §B3 helper 를 실행한다. `blocked` exit 3 은 정당한 대기 상태이며 milestone 완료가 아니다. 완료 시 `complete` → `compact` → `horizon-check`; active milestone 이 0개면 기본적으로 gap report 생성 후 멈춘다. 단 사용자가 명시적으로 continuation 을 요청한 경우에만 §B3 `Continuation opt-in` gate 로 다음 후보 승격 여부를 판단한다.

---
