---
name: session-end
description: >-
  세션 마무리에서 ROADMAP·cascade(OBJECTIVE/horizon)는 읽기만 하고 두 산출물을 쓴다: ① ROADMAP+cascade read-only preflight(현재 objective·horizon·active milestone·다음 차례·주의점 확인, 편집 금지) ② CLAUDE.local.md 핸드오프 덮어쓰기(다음 세션이 바로 이어받을 계획 위치·현재 상태·다음 할 일) ③ vault 40-Logs 저널 append(서사적 기록, 분량 제한 없음). ROADMAP milestone 상태 변경·150줄 compact·BACKLOG archive는 /harness가 소유한다. vault-write(단순 노트 저장)·session-log(로그만 append)·vault-recap(기간 recap)·weekly-review(주간 회고)·roadmap-update(ROADMAP만)와 다르다. 사용자가 "오늘 마무리할게", "세션 끝내자", "작업 끝났어", "전체 마감", "핸드오프까지 남겨줘", "/session-end" 라고 말할 때 반드시 이 스킬을 사용하라. 사용자가 "로드맵까지 정리해줘"처럼 ROADMAP 편집을 명시하면 /harness 또는 roadmap-update를 제안하고, session-end 자체로는 ROADMAP을 수정하지 않는다. 사용자가 "로그만", "append만", "session-end-light", "로드맵은 건드리지 말고"라고 하면 session-log를 사용한다.
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
codex: true
---

세션을 마무리한다.

## 목적 — 두 산출물, ROADMAP read-only

이 스킬은 **ROADMAP 을 참조만 하고, 성격이 다른 두 기록을 남긴다.** 혼동하지 말 것.

| 산출물 | 역할 | 수명 | 쓰기 방식 |
|---|---|---|---|
| `~/vault/40-Logs/YYYY-MM-DD.md` | **저널 / 책 재료** — 서사적 기록. 회고·집필 소스 | 영구 누적 | **append** (분량 제한 없음) |
| `CLAUDE.local.md` | **핸드오프** — 다음 세션이 바로 이어받을 현재 상태·다음 할 일 | 현재만 | **overwrite** |
| `ROADMAP.md` | **현재 horizon / 마일스톤** — 무엇을 했고 어디로 가는지 | 롤링 (150줄 cap) | **read-only** (`/harness` 소유) |

핵심 분담: vault 로그는 *깊게 쌓고*, local.md 는 *다음 할 일을 구체적으로 덮어쓰고*, ROADMAP 은 *읽어서 handoff context 로만 사용*한다. milestone 완료, `Status: [x]`, `status="completed"`, 150줄 compact, `BACKLOG.md` archive 는 `/harness` 가 소유한다.

아래 4단계를 순서대로 실행한다.

## 1. ROADMAP + cascade read-only preflight + CLAUDE.local.md 갱신

### ROADMAP.md (git 루트, read-only)

먼저 `ls ROADMAP.md` 로 존재를 확인하고, 있으면 **읽기만** 한다. 이 스킬은 ROADMAP 을 만들거나 수정하지 않는다.

preflight 에서 확인할 것:
- `ROADMAP.md` 존재 여부
- harness marker 존재 여부: `<!-- harness:milestone ... -->`
- active/pending milestone 대략 목록 또는 legacy checklist 의 남은 항목
- `line budget: <=150` 또는 실제 줄 수가 150줄을 넘는지
- `BACKLOG.md` 필요 여부 또는 존재 여부

금지:
- `ROADMAP.md` 신규 생성 금지
- `ROADMAP.md` 편집 금지
- `BACKLOG.md` 신규 생성/편집 금지
- `[x]`, `🔄`, `Status: [x]`, `status="completed"` 변경 금지
- `roadmap_sync.py compact` 실행 금지

ROADMAP 에 반영할 필요가 있는 상태 변화가 보이면 `CLAUDE.local.md` 의 주의점에 남긴다. 예:
```markdown
- ROADMAP 주의: M2 DoD는 충족된 것으로 보이지만 session-end는 ROADMAP을 수정하지 않는다. 다음 `/harness`에서 `roadmap_sync.py complete --milestone M2 ...` 확인 필요.
- ROADMAP 주의: 168 lines로 150줄 budget 초과. 다음 `/harness`에서 compact 필요.
```

### cascade 위치 (read-only)

다음 세션이 "지금 계획 어디에 있나"를 한눈에 잡도록, ROADMAP 위의 cascade 계층(ADR 0007)도 **읽기만** 한다. 있으면 top-down 으로:
- `docs/OBJECTIVE.md` — 북극성 한 줄 (없으면 cascade 미도입 repo → 이 블록 전체 skip)
- `ROADMAP.md` 의 `<!-- harness:goal -->` 가 가리키는 `docs/horizons/<slug>.md` — active horizon 목표 한 줄
- active milestone(`status="active"`) id·제목·`Status`·DoD 진행 한 줄
- **다음 차례** 추론 — 그 milestone 의 `docs/plans/<date>-<slug>.md` 에서 미완료 다음 step, 또는 milestone 완료 시 다음 후보 승격(§B3)·active=0 이면 "§B0.5 새 horizon 필요"

이 cascade 파일들도 **편집·생성 금지**(ROADMAP 과 동일 read-only). 읽은 결과는 아래 `### 계획 위치 (cascade)` 블록으로 `CLAUDE.local.md` 에 적는다. cascade 파일이 없으면 블록을 만들지 않고 넘어간다.

### CLAUDE.local.md (git 루트, Write 로 덮어씀)

핸드오프다 — **다음 할 일을 구체적으로, 넉넉하게** 쓴다. 인위적 cap 없음.

```markdown
## 이어서 할 일
> {today} 세션 종료 시 기록

- {다음 할 일 — 파일 경로·명령·현재 에러·왜 하는지까지 풀어서. 한 항목이 여러 줄이어도 좋다}
- {필요한 만큼}

### 계획 위치 (cascade)
- Objective: {docs/OBJECTIVE.md 북극성 한 줄}
- Horizon: {slug} — {목표 한 줄} (docs/horizons/{slug}.md)
- Milestone(active): {id} {제목} — Status {[ ]/[x]}, {DoD 진행 한 줄}
- 다음 차례: {다음 step / 다음 milestone 승격 / active=0 → §B0.5 새 horizon 필요}

### 현재 상태 / 주의점
- {어디까지 했고, 무엇이 열려 있고, 무엇을 조심할지 — 길이 제한 없음}
- {커밋·푸시 여부, 브랜치 상태는 거의 항상 포함}
- {ROADMAP read-only preflight 결과: active milestone, budget 초과 여부, 다음 /harness 에서 처리할 항목}
```

> `### 계획 위치 (cascade)` 는 cascade docs(`docs/OBJECTIVE.md`·`docs/horizons/`)가 있을 때만 쓴다. 없는 repo 면 이 블록을 생략한다(ROADMAP-only).

기준 = "다음 세션이 이 파일만 읽고 곧장 이어받을 수 있는가". `이어서 할 일`은 보통 **3~8개**, 각 항목을 짧게 줄이지 말고 **구체적으로 풀어쓴다**(모호어 금지: "테스트 마저" ❌ → "test_foo.py::test_bar 통과 — 현재 AssertionError at L42, 입력 fixture 가 None 인 게 원인으로 추정" ✅). `현재 상태`도 제한 없음.

변경 후 한 줄 요약 출력 (예: `ROADMAP: read-only 확인 | CLAUDE.local.md: 이어서 할 일 5건`). ROADMAP 이 없어도 생성하지 말고 `ROADMAP: 없음(read-only)` 로 보고한다.

## 2. vault 40-Logs 기록 (저널 — append)

**한 일 / 막힌 것 / 책 메모**를 작성해 헬퍼에 파이프한다. 헬퍼가 기기 레이블·날짜·파일명·헤더 생성·append 를 전부 처리한다. **이어할 것은 쓰지 않는다**(핸드오프는 local.md 담당). **분량 제한 없음** — 저널이므로 깊게.

```bash
PYTHONIOENCODING=utf-8 python3 ~/.claude/skills/session-end/bin/session-log.py <<'BODY'
한 일
  {무엇을 / 왜 / 어떻게 / 결과 / 배운 것 — 서사적으로, 길이 제한 없이}

막힌 것
  {미해결 문제 — 시도한 것 + 왜 안 됐는지. 없으면 이 항목 자체를 생략}

책 메모
  {인상적 장면·예상 밖 발견·삽질에서 배운 것·AI 관점 중 하나라도 있으면. 없으면 "없음"}
BODY
```

**작성 기준 (저널이므로 깊게):**
- **한 일** — 책·회고의 원재료. 단순 나열·요약 금지. 나중에 읽었을 때 그 세션이 복원될 만큼. **고친 대상 / 진짜 원인 / 검증 방법 / 남은 것**이 보이게:
  - ❌ 모호: "session-end 스킬 개선함. 비용 집계 고침."
  - ✅ 구체: "session-end 비용 집계가 늘 $0 나오던 원인 추적 → cost_tracker.py 가 Stop 훅인데 페이로드에 usage 가 없어서였음. transcript 파싱+모델단가 추정으로 재작성, 실세션 $28.30 정상 기록 확인. 이후 비용 스텝 자체를 의미 없다고 판단해 제거."
- **막힌 것** — 미해결 문제만. 없으면 항목 생략.
- **책 메모** — 해당 없으면 `없음`.

본문 작성은 stdin 으로만 넘기고, vault 경로·날짜·기기 레이블을 손으로 만들지 않는다(헬퍼가 처리).

> 저널 디렉터리는 기본 `~/vault/40-Logs/` 이고, `HARNESS_JOURNAL_DIR` 환경변수로 바꿀 수 있다(Obsidian vault 가 없거나 다른 곳에 로그를 쌓고 싶을 때).

## 3. (선택) harness evidence ledger 자동 갱신 (opt-in, non-blocking)

중앙 evidence ledger 를 운영한다면(여러 repo 의 하네스 작업을 한 곳에 모으는 collector), `HARNESS_EVIDENCE_REPO` 환경변수를 그 repo 로 설정해 두면 session-end 가 자동으로 갱신한다. **설정 안 하면 이 단계는 조용히 skip 된다 — 대부분의 사용자는 신경 쓸 필요 없다.**

```bash
EVIDENCE_REPO="${HARNESS_EVIDENCE_REPO:-}"
if [ -n "$EVIDENCE_REPO" ] && [ -f "$EVIDENCE_REPO/scripts/collect_harness_evidence.py" ]; then
  (
    cd "$EVIDENCE_REPO" || exit 1
    if command -v py >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 py -3 scripts/collect_harness_evidence.py
    elif command -v python.exe >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 python.exe scripts/collect_harness_evidence.py
    elif command -v python >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 python scripts/collect_harness_evidence.py
    else
      PYTHONIOENCODING=utf-8 python3 scripts/collect_harness_evidence.py
    fi
  ) \
    && echo "harness evidence ledger 갱신 완료: $EVIDENCE_REPO/evidence/generated/README.md" \
    || echo "harness evidence ledger 갱신 실패 — session-end 자체는 완료로 유지"
fi
```

원칙:
- 이 단계 실패(또는 skip)는 `session-end` 실패가 아니다. vault log / CLAUDE.local.md 기록은 유지한다.
- collector 는 이 패키지에 포함되지 않는다 — 본인 ledger repo 의 `scripts/collect_harness_evidence.py` 를 가리키게 한다.
- `session-log` 에는 이 단계를 붙이지 않는다. `session-log` 는 append-only 계약 때문에 repo 파일을 수정하면 안 된다.

## 4. 출력 + 완료

최종 답변은 **이번 세션 기록 + 다음에 할 일**을 한 화면에서 검토할 수 있게 다음 순서로 출력한다.

**(a) vault 저널 블록** — 헬퍼가 stdout 으로 **방금 기록한 엔트리를 그대로** 출력한다 (`── 기록한 세션 … ──` 블록 + `✓ … 기록 완료`). 그 출력을 **최종 답변에 그대로 포함한다** — 재타이핑하지 않는다(기록물과 100% 일치 보장).

중요:
- 기록 내용을 "vault에 남겼다"는 요약만 말하고 끝내지 않는다.
- `── 기록한 세션 ... ──` 블록부터 `✓ ... 기록 완료 (append)` 줄까지 빠짐없이 보여준다.
- 사용자가 방금 어떤 내용이 기록됐는지 확인할 수 있도록, 완료 문장보다 기록 블록을 먼저 출력한다.

**(b) 이어서 할 일 echo** — vault 블록 다음에, **1 단계에서 `CLAUDE.local.md` 에 방금 쓴 `## 이어서 할 일` 리스트를 그대로 다시 출력**한다. 이건 *display echo* 일 뿐이다 — 이어할 것의 실체는 `CLAUDE.local.md` 에만 있고(vault 저널에는 쓰지 않는다, 2 단계 분담 유지), 여기서는 사용자가 핸드오프를 같은 화면에서 확인하도록 재출력만 한다. 재타이핑하지 말고 방금 쓴 항목을 그대로 보여준다.

```
다음 세션에서 이어서 할 일 (→ CLAUDE.local.md):
- {1 단계에서 쓴 항목 1}
- {1 단계에서 쓴 항목 2}
- ...
```

**(c) 완료 메시지(고정 포맷)**:

```
vault 40-Logs 기록 완료 (append) | CLAUDE.local.md 핸드오프 갱신 | ROADMAP read-only 확인
```
