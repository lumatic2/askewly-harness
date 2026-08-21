---
name: harness-plan
description: >-
  하네스 흐름 1/3 — 계획. non-trivial 작업의 계획 분해와 승인을 담당한다(문서만 쓴다 — 구현·커밋 금지). 사용자가 "/harness-plan", "하네스 계획", "계획 깎아줘", "멀티스텝 계획 문서화", "마일스톤 계획", "step/단계별로 쪼개서 설계", "tooling changeset 시작", "프로젝트 방향 잡아줘"라고 말하거나, 승인되지 않은 non-trivial 작업을 시작할 때 사용한다. 승인된 계획 실행은 /harness-run, 완료 마감은 /harness-done, 단순 계획은 /spec, 신규 레포 초기화는 /harness-bootstrap.
---

# /harness-plan — 계획 깎기 → 분해 → 승인 (문서만 쓴다)

> **하네스는 흐름 3분할이다 (2026-07-23 C6)**: `harness-plan`(계획 — 문서만 쓴다) → `harness-run`(실행 — git 을 소유한다) → `harness-done`(완료 판정 → 마감 → 되먹임). 셋은 한 세트다 — 함께 배포·토글한다.
>
> **기계장치는 한 곳** — 3종이 부르는 스크립트는 전부 `harness-run` 의 `scripts/` 에 산다. `$HARNESS_SCRIPTS` 해석 (`~/.claude/...` 하드코딩 금지 — Codex 배포본 경로가 다르다):
> ```bash
> HARNESS_SCRIPTS="$HOME/.codex/skills/harness-run/scripts"
> [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness-run/scripts"
> ```

이 스킬은 **produce 구간**이다 — 계획·스캐폴드·문서만 쓴다. 구현코드·최종 산출물 생성·작업물 git 커밋 금지. 승인 등록까지 마치면 `/harness-run` 으로 넘어간다.

---

## 배치 규약 — 어디에 무엇이 사는가 (정본)

"이번 run 이 무엇을 만들지 선언"하는 의식도, 산출물 종류별 절차 분기도 없다(C10). 보는 것은 하나 — **어디에 무엇이 사는가.**

| 위치 | 무엇이 사는가 | 수명 |
|---|---|---|
| `CLAUDE.md` 「북극성」 절 (맨 위) | 북극성 — 사용자 소유, 방향만 (구 `OBJECTIVE.md` 흡수, C4) | living |
| `ROADMAP.md` (루트) | 상태판 — milestone 상태, ≤150줄 | living |
| `운영지도.md` (루트) | 운영 배선도 — 세션 생애주기·훅 배선·파일 파이프라인 (있는 레포만) | living |
| `plans/` (루트) | **현재·미래 계획만** — 작업 단위 계획서 `plans/<date>-<milestone-id>-<slug>.md` | living |
| `research/` (루트) | 리서치 산출물 `<date>-<소비처>-<slug>.md` — 양식 자유·저장 의무·소비처 백링크 | record |
| `archive/` (루트) | 완료·동결 기록 — `archive/plans/` (milestone 완료 시 이동)·은퇴 산출물 | record |
| `archive/reports/` | **최종 보고서** `<date>-<id>-<slug>.md` — 완료 의식 정본(/harness-done, 템플릿 `templates/REPORT_TEMPLATE.md`). ⚠ **git 추적 필수** | record |
| `changesets/` | tooling 변경 기록 (milestone 당 디렉터리 1개 — step 은 README 의 절, 기록-합본) | record |
| `docs/` | 도메인 문서 — PRD·ARCHITECTURE·ADR·BACKLOG·INDEX 등 (계획·리서치는 두지 않음) | mixed |
| `evidence/` | 측정·ledger | record |
| `.env`·시크릿 | 루트 `.env` (gitignore 필수) — 값 출력·커밋·로그 노출 금지 | local |
| 잡파일·임시 산출물 | **레포에 두지 않음** — 세션 scratchpad 사용 | ephemeral |

⚠ **`archive/` gitignore 충돌**: `report_close.py` 가 ignore 경로 보고서를 거부한다(실측 유실 19건). 걸리면 `python "$HARNESS_SCRIPTS/fix_report_durability.py" --root . --apply`(플릿 전체 `--fleet ~/projects`).

규칙: 폴더는 **lazy 생성**. 완료된 계획서는 완료 경계에 `archive/plans/` 로 이동, 이동 후 옛 백링크는 정정하지 않는다(record 동결). 구 배치(`docs/{plans,horizons,research,market}/`)는 폐지.

**무엇이 남는가** (기록 위치만 — 기본값 = changeset):

| 남는 것 | 기록 위치 |
|---|---|
| **변경**(코드·스킬·스크립트·문서) ★기본 | `changesets/<YYYYMMDD>-<slug>/` + 인덱스 — **milestone 당 디렉터리 1개**, step 은 README 의 절 |
| 분석 노트 / experiment | `references/<repo>/ANALYSIS.md`·`experiments/` + 인덱스 |
| 리서치 | `research/<date>-<소비처>-<slug>.md` |

- `.harness/manifest.json` 의 `packs_added` 는 무엇을 받았는지의 기록이지 레포 분류가 아니다 — run 판정에 쓰지 않는다(OI1).

---

## 탐색 — 계획 착수 진입 조건

계획(milestone 선택·논의·분해)에 들어가기 전에 차례로 확인한다. 이 구간의 쓰기는 리서치 산출물 저장뿐이다.

**1. 체크아웃 최신성 (첫 도구 호출 — 다기기 레포 필수)**: `python "$HARNESS_SCRIPTS/check_checkout_freshness.py" --root . --ttl 300`. **FAIL 이면 동기화 후 탐색** — 낡은 체크아웃은 기각된 설계를 되살린다. WARN 은 진행 가능하나 최신 보장 아님. "캐시" 출력이면 기각·회귀 단정 전 `--ttl 0` 재확인. **배포본-소스 어긋남을 "배포 회귀"로 단정하기 전에도 이 검사 먼저** — 소스 쪽 설계 변경일 수 있다.

**2. 필수 읽기**: `ROADMAP.md` + `CLAUDE.md`. 산출물 타입별 추가 읽기:

| 산출물 | 추가 읽기 |
|------|---------|
| changeset | 관련 `changesets/*/README.md` + 영향받는 `SKILL.md`/script/test/deploy 문서 |
| reference 분석/experiment | `docs/00-INDEX.md` + 관련 `references/*/ANALYSIS.md` |
| product 기능/화면 | `docs/PRD.md` + `docs/ARCHITECTURE.md` + (web) 루트 `DESIGN.md` 또는 token SSOT / (mobile) `docs/UI_GUIDE.md` + `docs/adr/` |

**3. 축적 데이터 회수 (새 기획 지점 진입 시)** — 에이전트는 아는 만큼만 계획에 담으므로, `research/` 선조회(「계획 작성」 리서치 항목이 정본)와 함께 askewly data 통합 회수를 1회 돌려 과거 결정 규칙·도구·실측 기록을 계획 재료로 가져온다:

```bash
[ -f ~/projects/the-notes-repo/bin/data.py ] && python ~/projects/the-notes-repo/bin/data.py recall "<이번 작업 주제>" --src agent --limit 3 || true
```

5축(일반지식·도구·나·세션기록·디자인) 라벨 병합 결과에서 이번 계획과 맞닿는 항목을 결정 로그·리스크 설계에 반영한다. 경로가 없는 환경이면 가드가 조용히 생략한다(설치 불요 — 선택 배선).

**공통 계층 — 2계층 (C4)**: `CLAUDE.md` 「북극성」 절(방향+규칙) → 작업 단위 계획서 `plans/<date>-<milestone-id>-<slug>.md`. horizon 층은 폐지. 새 에이전트는 이 둘과 `ROADMAP.md` 를 읽고 이어간다. **새 방향·신규 제품 기획은 계획서 생략 불가** — 「계획 작성」으로 설계 먼저.

## milestone 선택

`ROADMAP.md` 를 읽고 이번 run 의 **target milestone** 을 확정한다.

- active milestone 은 marker `status="active"` 만. `pending`/`blocked`/`error` 는 runnable 이 아니다.
- active 1개면 기본 target. 단 `Blocked by:` 또는 blocked·error 잔존 시 진행하지 말고 blocker 해소를 먼저 제시.
- active 여러 개면 `priority`·사용자 요청·blocker·다음 pending 을 대조해 1개 선택.
- 선택한 milestone 의 `DoD`·`Evidence`·`Gap` 을 계획·step 설계에 반영.
- 요청이 어떤 active 와도 부정합하면: **먼저 리프 판정으로 milestone-grade / step-grade 를 가른다.** step-grade(단일 changeset·좁은 수정)면 **새 milestone 을 만들지 않고** 기존 `Gap` 채우기 또는 *maintenance* 로 changeset 기록에만 남긴다 — milestone 제조 금지. milestone-grade(≥2 독립 step + 통합 검증 + 단독 capability)일 때만 「non-trivial 판정」을 거쳐 새 milestone 제안.
- active 0개면 새 구현에 들어가지 말고 `roadmap_sync.py gap-check` 로 gap 확인 후 멈춘다. 단 사용자가 이번 메시지에서 continuation("이어가"·"계속"·"run next"·후보 승격)을 명시했으면 pending/Next Candidate 1개를 active 로 승격 후 이 절 재시작. **새 milestone 을 *작성*해야 하면 「계획 작성」으로.**
- 정합성이 애매하면 추정 진행하지 말고 어느 milestone 에 연결할지 한 줄로 묻는다.
- **legacy ROADMAP**: unchecked 는 있는데 `harness:milestone` marker 가 없거나 active 0 = legacy. 체크리스트를 곧바로 실행 대상으로 보지 말 것. `roadmap_sync.py status` → 후보 제안 → **사용자 승인 후에만** marker 승격. 승인 전 정규화·구현·커밋 금지.

### 위계·스케일 루브릭 (리프 판정)

**용어 사전 (예약어):** 레벨 명칭은 **북극성 / Milestone / Step** + **changeset** 만 — 대체어·새 약어 발명 금지, 전 표면 동일 명칭. milestone ID = **`M<순번>`**(레포 전역 순번, 2026-07-31 사용자 확정 — 완료 ID 는 기록 동결), **ID 단독 언급 금지 — 항상 제목 동반**. step = plan doc 의 `step-N`. ~~Horizon~~ 은 폐지된 레벨.

북극성 → milestone → step 으로 분해한다. 규모는 **시간이 아니라 관측 가능한 테스트**로 가른다. 핵심은 **리프 판정** = "그만 쪼개라"의 정지 조건:

| 레이어 | 판정 테스트 | status 위치 |
|------|---------|-----------|
| **step (leaf)** | ① 한 coding pass 로 닫힌다 ② 단일 커맨드·체크 하나로 검증된다 ③ 한 레이어·모듈·파일셋만 건드린다 ④ 새 사용자 결정이 필요 없다 — **4개 다 충족 → leaf, 더 안 쪼갠다** | plan doc 의 step 체크박스 |
| **milestone** | step ≥2 + 가로지르는 통합 검증 ≥1 + 단독 capability·증거로 설명됨 (+ 사용자 결정을 부를 수 있음) → step 으로 쪼갠다 | ROADMAP `harness:milestone` (DoD/Evidence/Gap) |

위에서 아래로 적용해, 통과 못 하는 노드는 한 단계 더 쪼갠다. milestone DoD=통합 증거, step AC=구체 커맨드/파일 검증.

**크기 회고 (완료 경계)**: milestone 이 changeset 1개로 닫혔으면 그건 step 이었다 — 완료 보고에 라벨 정합 적발 한 줄.

⚠ **리프·규모 판정에 세션·시간 척도 금지**(예외 없음). 그릇 규칙(목표 전체·발명 금지·쪼개 팔기 금지)은 「계획 분해」 1 이 소유 — 무감독 길이는 목표 크기의 결과다(2026-07-31 사용자 결정).

---

## 논의 — 진입 지도

구체화·결정 사항을 사용자에게 제시하고 합의. Claude 는 AskUserQuestion 으로 묶어 묻고, Codex 는 합리적 기본값으로 진행하되 결정 없이 위험한 경우만 평문 한 줄 질문.

**두 방법 (FA1)**: 도메인·행동·취향=사용자 소유 → **캐묻는다(EXTRACT, 열린 질문)** · 기술=에이전트 → **제시한다(PRESENT = 논의 루프)**. load-bearing 에 "합리적 기본값" 제3선택지는 없다. non-trivial 진입 시 `references/elicit.md` 읽기.

**이 순간 한 번만 판정한다.** 아래 lane 은 같은 시점에 발화하므로 차례로 훑지 말고 해당 lane 만. 복수 해당이면 위에서부터.

| 무엇이 비었나 | lane | 하는 일 |
|---|---|---|
| 「북극성」 절·milestone 이 없거나 새 방향 | **계획 작성** | 북극성·Milestone 설계 (사용자 토론 — 소유권 경계) |
| **non-trivial**(아래 기준)인데 정체성 문서가 비었거나 미해결 결정 | **spec readiness** | 인터뷰→논의→기록 |
| 위 둘은 찼고 작업이 non-trivial | **non-trivial 판정** | 계획 내용 결정 |
| 위 셋 다 아님 (typo·marker·기계적 이어가기) | — | 한 줄 통과 후 「계획 분해」로 |

### spec readiness (정체성·결정 채우기) ★

> 정체성·PRD·TRD·핵심 결정을 채우는 단계의 소유자는 이 스킬이다(bootstrap 은 빈 스켈레톤만). step 설계·구현보다 먼저.

**트리거**: **이번 작업이 실제로 필요로 하는** 정체성 문서가 **없음/스켈레톤**이거나 **미해결 사용자 결정**이 있으면 발화.

어느 문서가 필요한지는 레포 분류가 아니라 **작업**이 정한다(OI1): 화면·기능 → `docs/PRD.md`+`docs/ARCHITECTURE.md`(+웹이면 `DESIGN.md` 또는 token SSOT) · 반복 업무 자동화 → `docs/DOMAIN.md`+`config/sources.md` · 레포 분석 → `docs/00-INDEX.md` · 도구·런타임 수리 → `CLAUDE.md`(source-of-truth·deploy 계약). 코어 밖 문서는 `--add <pack>` 으로 그 시점에 깐다.

절차: **스캐폴드 → (요구사항 불명확 시) 발견 인터뷰 → 논의 루프 → PRD/ADR 기록 → `docs(spec):` 커밋.** 논의 루프 = 결정 하나마다 [선택지+추천+근거] 제시, 사용자가 고른 것만 기록(추정으로 채우지 않는다). 이미 충실하면 한 줄 통과("spec 충분 — 실행 진입").

### 계획 작성 (북극성·Milestone) ★

**트리거** — 아래 중 하나면 해당 단계(각 단계 = 논의 루프 → `templates/` 작성 → `docs(spec):` 커밋):
- 「북극성」 절 없음/비어 있음 → **북극성 세우기 최우선** — 다른 단계보다 먼저, 본문은 한국어.
- active 0 + 사용자가 새 방향 원함 → Milestone 설계(리프 판정으로 milestone-grade 확인).
- 새 기획 지점 진입 시 **재료 수집(리서치)이 기본** — 에이전트는 아는 만큼만 계획에 담으므로 조사가 먼저다. 생략은 "조사 불요 — <이유>" 명시 시만. 산출물 `research/<YYYY-MM-DD>-<소비처>-<slug>.md`.
  - **리서치 규율 정본 = research-playbook-template** (`~/projects/the-orchestration-repo/docs/agent-os/templates/research-playbook-template.md`) — 있으면 복사 적용해 scope·질문·E-level(증거 등급 E1~E5)·source-map(URL·접근일·재검증)·envelope 로 규율한다. 경로가 없는 환경이면 자유 양식 + 전 인용에 출처 URL·접근일.
  - **착수 전 `research/` 선조회 의무 (2026-08-04 M12)** — 리서치 여부·생략 판단과 무관하게 새 기획 지점 진입 시 `research/` 를 Glob 으로 훑어 이번 주제를 덮는 기존 문서가 있는지 먼저 본다. 있으면 재리서치 대신 **인용 + 증분 갱신**(record 원본은 동결 — 갱신분은 새 문서로, 기존 문서 백링크). 왜: 조회 규약 없는 저장은 쓰기 전용이 된다(실측 같은 대상 3회 재조사).

**북극성 소유권 (2026-07-19 사용자 확정):** 문구는 **사용자 소유** — 에이전트는 후보 제안만, **명시 승인 후에만 기록**. 변경은 방향 자체가 바뀔 때만(Milestone 완료로 갱신 금지). 기계로 보호하지 않는다(ADR 0008).

**북극성 절 양식 정본 = 부트스트랩 스켈레톤**(`init-ai-readiness.sh`), 파서는 Stop 훅 `plan_position_stop`. 지킬 것 하나: **북극성 문구를 인용구·하위 제목 안에 넣지 않는다**(첫 일반 문단 첫 문장이 매 턴 표시된다).

**후보 백로그**: `ROADMAP.md` 의 `pending` 마커 — **순서는 사용자 소유**, 에이전트는 후보·근거 제안만.

기존 milestone 이어가기·후보 승격은 여기로 오지 않고, cascade 없는 레포는 건너뛴다. 작성 후 「milestone 선택」→「계획 분해」로.

### non-trivial 판정과 계획 내용

**non-trivial 기준** — 하나라도 해당: 여러 task/file/session 에 걸침 · product behavior·API·data model·권한·결제·외부 연동·배포면 변경 · security·secret·supply chain·protected file 영향 · 기존 spec/ROADMAP/ADR/과거 판단과 충돌 가능성 · 외부 제품·사례의 반영 여부 판단 필요. 반대로 typo·format·README/CHANGELOG · marker/status 갱신 · 정답이 고정된 좁은 버그 수정 · 기계적 이어가기는 가볍게(진입 지도 마지막 행).

non-trivial 이면 아래를 **판단해 결정하고 결과만 적는다** — 안 하면 실제로 틀리는 것들이다.

- **DoD 에 검증 1개 + 실패 모드 1개.** source 변경은 lint/test/smoke/review 중 하나 이상을 DoD 에 넣고, happy-path 만으로 완료 처리하지 않는다 — 없는 source·실패 커맨드·auth 경계·빈 데이터·rollback·배포 미반영 중 하나를 확인. 실패 경로 확인 불가면 결과는 partial.
- **표면에 맞는 E2E 구동이 DoD 필수.** lint/test 통과로 "됐다" 하지 않는다. **웹/UI** → 개발서버+실제 브라우저 · **CLI/스크립트** → 실행+출력·exit code · **API** → 실요청+응답·부작용 · **데이터/배치** → 1회 구동+행수·스키마. 구동 불가 환경이면 그 사실과 대체 검증 명시, 결과는 partial.
- **위임 여부를 명시 결정** — `use | skip | ask_user` + 이유. 비용·원격·권한·대규모 병렬화는 `ask_user`. 위임 시 child 결과를 완료로 믿지 말고 parent 가 검증해 evidence ledger 로 닫는다. 위임 규약은 자기 런타임의 서브에이전트 문서를 따른다.
- **spec/ADR/ROADMAP 반영 변경이 있으면 적고, 없으면 생략 이유를 적는다.**
- **secret 은 읽지 않는다** — `.env`·토큰 확인 필요 시 Risk Gate 로 정지.
- **high-risk(보안·결제·마이그레이션·대규모 diff·배포면)** 는 완료 시 spec/quality 축 분리 판정 + near-miss 기록. low-risk 는 단일 판정.
- **repo 가 크면 scoped `AGENTS.md`/`CLAUDE.md` 존재 확인**, 없으면 final 에 context landmark 후보로.

---

## 계획 분해 (scope 결정 + plan doc)

milestone 이 여러 step 이거나 세션을 넘겨 이어받을 작업이면, 실행 전에:

1. **scope 경계** — 이번 run 이 닫을 범위 + 중단점(검증 PASS·blocked·budget). 결정 지점 3 facet: milestone 선택=어느 milestone · 여기=어디까지 · 연쇄(/harness-done)=다음 승격. scope 가 사용자 소유면 논의 루프로 묻는다. **그릇 기본값 = 사용자가 준 목표 전체 (2026-07-31 사용자 결정)**: 목표가 여러 milestone 을 품으면 연쇄를 전부 펼쳐 결정 소진을 연쇄 전 범위로 하고, 승인 1회에 `--chain` 으로 등록한다. 탐색적이라 끝이 안 보이면 보이는 데까지 담고 예상 정지 지점 명시.
2. **계획 분해 → plan doc** — 리프 판정으로 leaf 까지 쪼개 `plans/<YYYY-MM-DD>-<milestone-id>-<slug>.md`(템플릿 `templates/PLAN_TEMPLATE.md` — 없으면 `bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh . --add cascade`)에 박는다. 각 leaf 는 승인 전에 `Artifact`·`Risk`·정확한 `Files`·`Dependencies`·`Verify`·`Failure probe`·`Commit` 완비. plan 전체에 `execution mode: continuous`·hard-stop policy·범위/중단점(절 제목 `## run 전 scope 결정`)·rollback/cleanup. 실행은 scaffold 를 재해석하지 않고 구현 세부만 보충. 위계 섹션은 「북극성」 절로 백링크.
   - **장부 권위 (2026-07-22 사용자 확정)**: plan doc 은 *에이전트가 자기 진행을 체크·기록하며 나아가는 장부*다. step 을 끝낼 때마다 `- [ ]`→`- [x]` — **체크박스가 진행의 쓰기 정본**, 승인 hash 는 체크박스 상태를 봉인하지 않는다(MM7).
   - 계약 본문(step 정의·Files·Verify·범위·중단점)은 승인 후 불변. `.harness/work.json` 의 `steps[]` 는 체크박스에서 파생되는 포인터 — 어긋나면 plan 이 이긴다. 이 plan doc 으로 새 에이전트가 몇 시간 이어받는다.
   - **`Dependencies:` 는 기계 판독된다 (OI2).** 문법 정본 `templates/PLAN_TEMPLATE.md` 머리말. `validate_plan_gate.py` 가 순환·미아 참조를 잡고, 다음 착수 가능 leaf 와 동시 가능 집합이 파생된다. 횡단 단계(배포·출고·재생성)는 `## 재생성 장벽` 절에.
3. **결정 사전 소진 (plan-hardening)** — `## 결정 로그` 에 **사용자 소유 결정**을 전부 나열해 계획 단계에서 매듭. 없으면 "없음" 명시(빈 섹션 금지). **승인 후에는 예상 밖 중요 결정(신규 리스크·스코프 변경·크레덴셜)이 아닌 한 추가 질문 없이 무중단 진행.**
   - **표면 열거 → 소진 (FA1)**: manifest + 4렌즈(구조/행동/기술/계약) 전수 열거 → 방화벽(근거됨→실현 / 튜닝값→기본값 / **assumed 만 질문**). **assumed 잔존 = `resolved` 불가.** 상세 `references/elicit.md`.
3-b. **배차 설계 (선택 절 — M18 2026-08-14 · M23 2026-08-22 확장)** — 동시 가능 leaf ≥2 **또는 단가 이득**(명세 고정 + Risk `기계적`/`없음` 인 구현 노동은 순차라도 하위 모델 워커가 기본 — 2026-08-22 사용자, 정본 `delegation.md` 「단가 이득」)이 있으면 plan doc 에 `## 배차 설계` 절을 쓴다. 절 문법·행 문법의 정본은 `templates/PLAN_TEMPLATE.md` 머리말 — 핵심 둘만 여기 적는다: ① worker 행이 있으면 **`- 계획 모델:` 줄 필수**(게이트가 워커 모델 ≤ 계획 모델 상한을 검사 — sonnet 계획이 opus 워커를 부리는 역전 차단, 발효 2026-08-22) ② 절이 없으면 실행은 전부 인라인(현행 유지). 소비는 `/harness-run` fan-out·워커 배차 절.
4. **아는 만큼만 펼친다** — 탐색적 작업은 다음 1~2 leaf 만 확정하고 나머지는 finding 큐로. up-front 완전 분해 강요 금지.
5. **면제 + 과분해 금지**: 단일 step·가벼운 작업, 분석(1 ref=1 step)은 평면 — 재귀 면제. **★기본 단위 = 1 step = 1 응집 변경 = 1 커밋.** 한 응집 변경이면 파일·검증이 여럿이어도 1 step — **여러 검증 단계 ≠ 여러 step**(검증은 Verification 체크리스트로). 기록 위치·단위는 배치 규약 「무엇이 남는가」 표가 정본(OI5 — 재서술 않음, 2026-08-15 M20 통합). plan doc·milestone 은 **≥2 독립 step + 통합 검증**일 때만. 한 step 을 4-leaf 로 펴는 건 과분해(F2/T3).
6. **plan 기계 lint** — multi-step 이면 실행 전 `python "$HARNESS_SCRIPTS/validate_plan_gate.py" <plan>`. 필수 항목·placeholder·의존 그래프는 **게이트가 말해준다** — 수기 복창하지 않는다.
   - **승인 전 점검은 `--pre-approval` 로 돌린다** (M6 2026-08-20). 승인 전 계획서는 정의상 draft 라 그냥 돌리면 게이트가 **항상 빨갛고**, 그래서 "Status 하나만 남고 나머지는 통과"라는 판정에 사람이 매번 꼈다 — 그 문장에 진짜 위반이 섞이면 그대로 넘어간다. 이 플래그는 **Status 값 판정 하나만** 면제한다: `Status:` 줄 부재·필수 항목 결손·Risk 어휘 위반·결정 로그 미소진은 플래그가 있어도 FAIL 이다. 승인 등록(`approve_harness_plan.py`)에는 흘리지 않는다 — 거기서는 승인 어휘를 실제로 요구한다.

**스캐폴딩 결정 (CS6→HQ2).**
- plan doc 의 `## 스캐폴딩 결정` 은 3층: 범용 코어 3(`source-of-truth`·`검증`·`배포/운영`) / 자기선언 도메인(선언한 것 전부 채움 — 빈 값=FAIL) / `- 검토 후 제외:` 1줄. `validate_plan_gate` 가 기계 검증.
- 미결 도메인은 인터뷰로 전부 소진한 뒤에만 승인 요청. **구현 중 새 사용자 소유 결정 발견 = 설계 실패로 계수**(`ledger_append.py interruption --reason decision_required`).
- **승인은 계획서 전체 단위** — 부분-위임 폐지(2026-07-21). 작아 보이면 사용자가 "확장"으로 답한다.
- 3층 정의·검증 문법의 정본은 `validate_plan_gate.py` 와 `templates/PLAN_TEMPLATE.md` 머리말(사본 금지).

## 승인 게이트

**멀티스텝이면 기본 정지·제시·승인; 단일/가벼움이면 통과.**

- **fresh 계획 검증자 (FA1)** — 멀티스텝은 승인 요청 전 1회: **`plan-verifier` 정의를 그 런타임의 위임 경로로 1회 스폰하고, 모델은 인자로 지정하지 않는다**(정의가 소유 — 지정하는 순간 덮인다). 정의는 Claude·Codex **양쪽에 배포된다**(M3 2026-08-19 — Claude `~/.claude/agents/plan-verifier.md`, Codex `~/.codex/agents/plan_verifier.toml` — 이름의 하이픈이 밑줄로 바뀌는 것은 Codex 이름 규칙이다. 출고 계약은 `custom-skills/agents/README.md`). 무엇을 사냥하고 무엇을 돌려주는지는 그 정의가 소유하므로 프롬프트에 복제하지 않는다. **자문형** — 발견 반영+요지 1줄을 승인 제시에, 게이트=사용자(ADR 0008). pass-through 면제. 상세 `references/elicit.md` §백스톱.
  - **그 정의를 받지 못한 런타임이거나 위임이 막힌 환경이면 자기 재검토 1회로 대체** (2026-08-05 실측 · 2026-08-19 M3 로 조건 확장): 조건이 둘인 이유는 실측이다 — Codex 는 위임이 열려 있는데 정의만 없어서 구 조건("위임이 막힌 환경")에 안 맞았고, 그래서 FA1 이 대체 사실 한 줄도 없이 증발했다. 대체 절차는 ①수치·경로 실측 ②미소진 결정 ③leaf 위반만 재훑고 **승인 제시에 "fresh 검증자 대체: 자기 재검토(정의 미배포 또는 위임 제한)" 한 줄**을 적는다. 금지는 대체 사실 누락뿐 — 검증 생략도, 위임 가부를 되묻는 정지도 아니다.
- **멀티스텝 milestone** → **기본 정지.** 실행 전 계획을 제시하고 *명시 승인*을 받는다. **승인("ㄱㄱ") 전 실행 진입·구현코드 변경·커밋 금지(하드 차단).**
  - **제시 방식**: 아래 "계획 제시 형식"으로 보여준 뒤 **그 ⑦의 3안 문자열을 그대로 평문 질문으로 써서 턴을 끝낸다 — 같은 턴에 AskUserQuestion 금지**(모달이 제시를 덮는다 — F1). AskUserQuestion 은 선택지가 자기완결인 결정에만.
    - ⚠ **질문 문자열을 여기에 다시 적지 않는다.** 정본은 ⑦ 한 자리뿐이다 — 두 곳에 서로 다른 문자열이 있으면 먼저 읽은 쪽이 이겨서 승인 어휘가 조용히 축소된다. (2026-08-15 실측: 이 줄이 실행 위치 3택을 뺀 축약 문자열을 들고 있었고, 그게 ⑦을 덮어 사용자가 새 세션·워크트리 선택지를 못 받았다. 세션이 옛 배포본을 물고 있어서가 아니라 문서가 자기 자신과 어긋나 있었다. 그래서 여기에는 축약본조차 예시로 남기지 않는다.)
  - **답의 의미 — 승인 어휘 3분화 (M21 2026-08-15)**: 승인은 실행 위치까지 함께 답한다 — **`ㄱㄱ`** = 같은 턴 실행(기본, 단독 "ㄱㄱ"는 언제나 이 뜻) · **`새로ㄱ`** = 승인 등록+`docs(plan):` 커밋까지 마친 뒤 이 세션을 마감 — 새 세션을 열고 "이어가"로 이어받는다. 그 외: "확장"=과소 판정 → 더 담아 재제시 · "수정"=반영 후 재제시 · 중단은 상시 가능.
  - **승인 등록은 실행할 체크아웃에서**: 승인 직후 `python "$HARNESS_SCRIPTS/approve_harness_plan.py" <plan> --root <repo> --work-id <id> --milestone-id <id> --changeset-path <path> --session-id <runtime-token>` 을 **실행할 바로 그 체크아웃(워크트리)에서** 실행해(승인받은 연쇄는 `--chain <id,id>` — 미제시 id 금지) plan SHA-256 approval receipt 와 active work 를 원자 등록 — work.json 은 checkout-local(HQ1). 승인 hash 가 현재 plan 과 다르거나 receipt 가 없으면 실행/continuation 금지.
  - **승인 커밋 — 등록 직후 즉시 (2026-08-04 M12)**: plan doc(+ROADMAP marker 갱신분)을 `docs(plan): <milestone 제목> 계획 승인` **단독 커밋**으로 남기고 push 한다. 왜: 영수증은 gitignored 라 이 커밋이 git 이력의 계획-구현 대조 기준점이다(실측: M10·M11 계획서가 구현 커밋에 동승). "구현코드 커밋 금지"와 모순 아님 — 계획서는 계획 문서다(produce boundary 는 `plans/` 를 차단하지 않는다).
  - **봉인 범위** — 승인 hash 는 step 체크박스 *상태*를 봉인하지 않고(MM7), **append-only 절(`## finding 큐`·`## 진행 로그`)의 *내용*도 봉인 대상이 아니다**(cs#357). 그 밖의 본문과 **절 제목 줄**은 봉인 — 바꾸면 차단.
  - **소유자 판정 정본은 env `CLAUDE_CODE_SESSION_ID`**, `--session-id` 는 env 없는 런타임용 기록 토큰 — 둘이 다르면 approve 가 경고.
  - **승인 커밋 직후 같은 턴 run 진입 (run-008)**: 등록·커밋은 종착점이 아니다 — 같은 턴에 `/harness-run` 으로 step-1 착수까지. "승인되었다" 보고만 하고 턴 종료 금지(ㄱㄱ 2회 실측 갭). 이 규칙은 `ㄱㄱ`(같은 턴) 답에 적용 — `새로ㄱ` 는 그 절차가 종착점이다(M21).
- **단일 step·가벼운 작업** (분석 1 ref, 단일 changeset, typo·marker·기계적 이어가기) → **pass-through.** "produce 끝 → run 진입: …" 한 줄 통지만 하고 `/harness-run` 으로. (단 사용자가 "실행 전에 멈춰"·"계획 먼저" 명시 시 단일 작업도 제시·승인.)

**계획 제시 형식 (멀티스텝 정지 시).** plan doc 을 그대로 던지지 말고 ① 산문 요약(무엇을·왜) ② 체크박스 step 트리(+verify) ③ 핵심 결정·리스크·중단점 ③′ **검증자 지적 처분 요약** — 계획 검증자를 붙였으면 지적 n건 중 반영/부분 반영/기각이 몇이고 기각 이유가 무엇인지 한 줄(계획서의 `## 검증자 지적 처분` 절이 정본, 강제는 아니다) ④ plan doc 경로 + run 영향 ⑤ **무감독 전망** — 이 승인으로 개입 없이 어디까지 가는지: 연쇄 milestone 목록+한 줄 요지+예상 정지 지점, 연쇄가 비면 왜 1-milestone 인지 한 줄 ⑥ **실행 위치 = 승인 어휘** (M21 2026-08-15) — `ㄱㄱ` 같은 턴(기본) / `새로ㄱ` 새 세션(등록·커밋 후 이 세션은 마감 — 새 세션을 열고 "이어가"로 이어받는다). 무언이면 같은 턴. 에이전트는 실행 위치를 권고할 수 있는데 **기준은 수치다** (D7 2026-08-20 사용자 확정): **fable·opus 는 컨텍스트 사용률 20% 미만이면 `ㄱㄱ`, 20% 이상이면 `새로ㄱ` 를 권고**하고, 그 밖의 모델은 이 기준의 대상이 아니다. **권고에는 판정 근거 수치를 함께 적는다 — 수치를 못 대면 권고하지 않고 3택만 제시한다**(2026-08-20 실측: 실측 없이 '여유가 충분하다'고 인상으로 권고했다가 적발됐다. 구 30~40% 경계 문구는 이 기준으로 대체됐다). **수치 출처 = 터미널 status line 의 `ctx:NN%`** (`~/.claude/statusline.sh` 가 `context_window.used_percentage` 를 표시) — 에이전트 화면에는 이 값이 안 들어오므로, 다른 데서 찾아 헤매지 말고 승인 질문에 "status line 의 ctx 값을 알려달라"를 함께 물어 그 수치로 판정한다(2026-08-21 실측: 출처 미기재로 세션이 확인 위치를 못 찾고 헤맸다) ⑦ **승인 질문 3안 고정**("승인(ㄱㄱ — 새 세션이면 새로ㄱ) / 확장 — 범위를 더 담아 재제시 / 수정") 순. 문서만 만들고 요약 없이 넘어가기 금지.

미해결 사용자 결정이 남았으면 진행 승인부터 받지 말고 논의 루프 [선택지+추천+근거]로 먼저 매듭짓는다(승인 질문에 합쳐도 됨).

**필수 정지 예외.** target milestone 부재·요청-milestone 부정합·legacy 정규화·새 milestone 추가는 pass-through 도 하지 않는다 — 제안만 하고 사용자 승인 전 실행·구현·커밋 **금지**. 새 계획 *작성*이면 「계획 작성」으로.

단, 같은 turn 에 continuation 명시 + 기존 pending/Next Candidate 그대로 승격이면 "승인된 후보 실행"이다 — 승격 후 「milestone 선택」으로(멀티스텝이면 승인 게이트 재적용).
