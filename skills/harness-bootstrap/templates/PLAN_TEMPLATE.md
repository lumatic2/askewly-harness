# PLAN — {milestone 제목}

> 생성: {YYYY-MM-DD} · 산출물: {changeset | 분석 노트·experiment | playbook | phase} · scope 결정: {이번 run 이 어디까지}
> milestone-레벨 durable plan doc. Claude/Codex 가 이 문서만 읽고 이어받는 단일 장부.
> 세부 step 상태는 이 문서의 **체크박스가 쓰기 정본**이고, 산출물별 status machine(`phases/index.json` / `changesets/README.md` / `run.json`)은 거기서 파생되는 포인터다.

Status: {draft → 승인 시 approved (날짜·승인 문구) → 완료 시 completed}

## 북극성 → milestone → step (위계 — 2계층, horizon 층은 2026-07-23 C4 폐지)
- **북극성**: {한 줄} (← `CLAUDE.md` 맨 위 「북극성」 절)
- **milestone**: {이번 milestone + 왜 이 규모인가(리프 판정상 milestone인 근거)}

## run 전 scope 결정 (확정)
- **결정**: {이번 run 이 닫을 step 범위}
- **execution mode**: `continuous`
- **중단점(stop points)**: completed / 증거가 있는 blocked / decision_required / risk_gate / secret_required / external_authority_required / user_stopped
- **진행 보고**: commentary only. 미완 leaf 는 턴 종료점이 아니다.
- **rollback/cleanup**: {changeset별 되돌리기 및 임시 자원 정리 방법}

## 스캐폴딩 결정 (CS6 범용화 — validate_plan_gate 가 기계 검증, 결정 없이 위임 금지)
> 코어 3 + 이 작업에 필요한 도메인을 스스로 선언해 전부 채운다. 기본값 소스: `~/.claude/memory/dev-stack.md`, 디자인은 Askewly Design 진입 프로토콜(ui.askewly.com). 안 걸리는 도메인은 값에 `해당 없음 — <이유>`.
- source-of-truth: {정본이 어디 사는가 — 레포/파일/서비스}
- 검증: {무엇으로 검증하는가 — 테스트·스모크·E2E 표면}
- 배포/운영: {어떻게 도달·운영되는가 — 호스팅·동기화·env·관측 / 해당 없음 — <이유>}
<!-- 아래는 자기선언 도메인 — 이 작업에 걸리는 것만 추가 (서비스형 참고 카탈로그: 화면·서버·데이터·디자인·배포·관측 → planning-gates.md) -->
- {도메인}: {결정 내용}
- 검토 후 제외: {검토했으나 안 걸리는 표준 도메인 — 이유 / 없음}

## 결정 로그 (run 전 사전 소진 — /harness-plan 계획 분해)
> 이 milestone 실행 중 나올 수 있는 사용자 소유 결정을 계획 단계에서 전부 매듭. 없으면 "없음" 명시(빈 섹션 금지).
- {결정 1: 선택지 → 확정값 (근거·확정일)} / 없음
<!-- 매듭 완료면 resolved, 애초에 결정이 없으면 none-required -->
- status: resolved


## Step 트리 (실행 전 계획 분해 — 리프 판정로 leaf까지 펼침)
> 목표→milestone→step→spec 으로 위에서 아래로 쪼갠다. 각 노드가 리프 판정(① 한 coding pass ② 단일 검증 ③ 한 surface ④ 새 사용자결정 없음)를 통과하면 leaf. 아는 만큼 펼치고(못 펼치면 다음 1~2 leaf만) 나머지는 finding 큐로.
> **`Dependencies:` 는 기계 판독된다** (2026-07-23 OI2) — 값은 `none`(또는 `없음`) 이거나 `step-N` 나열(쉼표/공백)이고, id 뒤에 **괄호 꼬리말 1개**로 *왜* 그 의존인지 적을 수 있다(`step-2 (게이트 형식 확정 후)`). 괄호 밖 산문은 게이트가 거절한다. 여기서 **다음에 착수 가능한 leaf 와 동시 가능 집합이 파생**되므로, 순서를 적는 자리가 아니라 **무엇이 끝나야 시작할 수 있는지**를 적는 자리다. milestone 사이의 의존은 여기 쓰지 않는다 — 그건 horizon 설계서와 ROADMAP marker 소유다.
> **`Risk:` 는 배차와 검증 두께를 정한다** (2026-07-23 DC1) — `위험`·`기계적`·`없음` 중 하나, 판단이 안 서면 `미분류`(게이트가 따로 집계하고 위험 쪽으로 취급한다). 가르는 질문은 하나다: **이 변경으로 지금까지 통과하던 것이 막히기 시작하는가.** 막히기 시작하면 `위험`(오탐이 정상 작업을 세운다), 막히는 집합이 그대로면 `기계적`, 산출물이 기록뿐이면 `없음`. 등급은 *의식의 크기*만 정하지 테스트 면제권이 아니다 — 실제 위험이 있는 동작을 검증 없이 두면 등급과 무관하게 미달. 소비 규칙(등급별 실행 모드·배차 이득 체크리스트)은 `~/projects/the-orchestration-repo/context/delegation.md` (2026-07-23 재조립 P1 로 구 `references/delegation.md` 에서 이전).
> **진행의 쓰기 정본은 이 체크박스다** — step 을 끝낼 때마다 그 자리에서 `- [ ]`→`- [x]` 를 켠다(승인 해시는 체크박스 *상태*를 봉인하지 않는다, MM7). 산출물별 status machine(`phases/index.json`·changeset 표·`run.json`)과 `work.json` 은 여기서 파생되는 포인터이고, 어긋나면 plan 이 이긴다. ~~구 서술: 진행 권위는 status machine 이 정본, 체크박스는 boundary 에서만 동기화~~ — **폐기 (2026-07-23)**, 근거였던 이중기록 drift 는 파생 전환(cs#353)으로 해소됐다.

## 이 문서의 내용 계약 (2026-07-17 CS5)
> **적는 것**: step 트리(leaf 필드 완비)·스캐폴딩 결정·결정 로그·검증/DoD·scope 경계. 승인 후 본문은 불변(실행 계약).
> **적지 않는 것**: 실시간 진행 상태(→ `.harness/work.json`·산출물 status machine 정본) · 도메인 지식 본문(→ docs/·research/ 링크) · 완료 후 회고(→ changeset Result·BACKLOG).
- [ ] **step-1 — {slug}**
  - Artifact: {완료 시 존재할 산출물/동작}
  - Risk: {위험 | 기계적 | 없음 | 미분류} ({한 줄 근거})
  - Files: {읽을 파일 + 수정할 정확한 파일/surface}
  - Dependencies: none
  - Verify: {AC를 판정할 명령/체크}
  - Failure probe: {반드시 실패해야 하는 negative-path 검증}
  - Commit: {이 leaf의 changeset/commit 경계}
- [ ] **step-2 — {slug}**
  - Artifact: {완료 시 존재할 산출물/동작}
  - Risk: {위험 | 기계적 | 없음 | 미분류} ({한 줄 근거})
  - Files: {읽을 파일 + 수정할 정확한 파일/surface}
  - Dependencies: step-1
  - Verify: {AC를 판정할 명령/체크}
  - Failure probe: {반드시 실패해야 하는 negative-path 검증}
  - Commit: {이 leaf의 changeset/commit 경계}
  - (더 쪼갤 필요 있으면 하위 leaf 로)

## 배차 설계 (선택 — 동시 가능 leaf 가 있고 배차 이득을 살 때만, 2026-08-14 M18)
> **opt-in**: 이 절이 없으면 게이트는 아무것도 요구하지 않는다. 쓰는 조건 = Dependencies 파생 동시 집합에 leaf ≥2 + 배차 이득 체크리스트(`~/projects/the-orchestration-repo/context/delegation.md`: 파일 격리·독립 시각·컨텍스트 격리·벽시계 단축) 중 ≥1 을 실제로 산다.
> 행 문법(게이트가 검사): `- step-N · inline|worker(<model>) · 격리 none|worktree · 검증 <equivalent 경로/커맨드>` — worker 행은 model 필수, 참조 leaf 는 실재해야 하며, 서로 의존하는 두 leaf 를 worker 로 병렬 선언하면 차단된다. **이 절을 가진 계획의 승인(ㄱㄱ)이 곧 그 규모 fan-out 의 사전 승인이다** — 절에 없는 즉흥 fan-out 은 여전히 건별 승인(글로벌 규약).
- 근거: {배차 이득 항목 — 무엇을 사는가}
- {step-N · worker(sonnet) · 격리 worktree · 검증 …}

## 재생성 장벽 (선택 — wave 사이에 한 번 도는 횡단 단계)
> 특정 step 들이 끝난 뒤 **다음 leaf 를 시작하기 전에** 한 번 돌아야 하는 것. 배포·훅 출고·인덱스
> 재생성이 여기 해당한다(지금까지는 사람이 기억해서 돌렸다). 없으면 이 절을 지운다.
- after: {step-N, step-M} · run: `{명령}`

## 검증/DoD
- **DoD**: {milestone 완료 판정 — 통합 증거}

## finding 큐 (작업 중 발견 — 다음 step/changeset 으로 흘림)
- {F1 …}

## 진행 로그 (append-only)
- {날짜 · step-N 완료 (cs#NNN) — 한 줄. 서사 금지, 다음 세션에 필요한 사실만}

<!--
~~진행 로그 절을 두지 않는다 (2026-07-21 CF3 step-4)~~ — **폐기 (2026-07-22 SS4 step-2).**
CF3 의 근거는 "승인 해시가 본문 추가를 차단한다" 는 기술적 사유 하나뿐이었는데,
cs#357 이 append-only 절의 *내용*을 봉인에서 빼면서 그 사유가 사라졌다. 근거가
사라진 결론은 유지하지 않는다. 반대편에는 살아 있는 근거가 있다 — 계획서는
에이전트가 자기 진행을 체크·기록하며 나아가는 장부다(cs#353, 사용자 확정).
절의 제목 줄은 여전히 봉인되므로 지우거나 이름을 바꾸면 continuation 이 막힌다.
-->

