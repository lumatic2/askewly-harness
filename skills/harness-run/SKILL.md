---
name: harness-run
description: >-
  하네스 흐름 2/3 — 실행. 승인 영수증이 등록된 계획(plan doc)의 step 을 무개입으로 구현·검증·커밋한다(git 은 이 스킬이 소유). 사용자가 "/harness-run", "하네스 실행", "승인된 계획 실행", "이어가", "계속", "run next"라고 말하거나, 승인된 active work 를 이어받을 때 사용한다. 계획·승인이 아직이면 /harness-plan, milestone 완료 경계 마감은 /harness-done. 3종 스킬이 공유하는 기계장치 스크립트는 이 스킬의 scripts/ 가 보관한다.
---

# /harness-run — 무개입 실행 → 검증 → 커밋 (git 을 소유한다)

> 하네스 3종 세트의 실행 단계: `harness-plan`(계획) → **`harness-run`** → `harness-done`(완료). 셋은 한 세트다 — 함께 배포·토글한다.
>
> **기계장치는 한 곳** — 3종이 부르는 스크립트는 전부 이 스킬의 `scripts/` 에 산다. `$HARNESS_SCRIPTS` 해석 (`~/.claude/...` 하드코딩 금지 — Codex 배포본 경로가 다르다):
> ```bash
> HARNESS_SCRIPTS="$HOME/.codex/skills/harness-run/scripts"
> [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness-run/scripts"
> ```

실행은 **인라인**이다 — 에이전트 자신이 step 을 수행하고 외부 subprocess 를 띄우지 않는다. (구 `scripts/execute.py` 는 2026-08-07 제거됐다: `phases/index.json` 모델 위에서 도는 무인 엔진이었는데, 그 모델 자체가 2026-07-23 재조립 P4 에서 `docs/plans` + `.harness/work.json` 으로 대체됐다. 기존 레포의 `phases/` 디렉터리는 과거 기록으로 남는다.)

## 진입 조건 — 승인 영수증

- run 은 **승인된 계획 위에서만 돈다.** `.harness/work.json` 에 approval receipt(plan SHA-256)가 있고 hash 가 현재 plan 과 일치해야 한다 — 없거나 어긋나면 실행·continuation 금지, `/harness-plan` 으로 돌아간다.
- 승인 등록(approve)은 **실행할 바로 그 체크아웃**에서 이뤄졌어야 한다(work.json 은 checkout-local, HQ1). 다른 체크아웃의 approve 는 이 워크트리를 지키지 못한다.
- 단일 step·가벼운 작업(계획서 없는 pass-through)은 receipt 없이 진행하되, `/harness-plan` 의 한 줄 통지("produce 끝 → run 진입: …")를 거친 것이어야 한다.
- **영수증이 보장하는 것은 "무엇이" 승인됐나지 "누가" 승인했나가 아니다** (2026-08-06 외부 감사 #1). `approved_by: "user"` 는 `approve_harness_plan.py` 가 무조건 기록하는 상수이며, 에이전트가 그 커맨드를 직접 실행하면 그대로 만들어진다 — 이 장치는 **계획 본문을 SHA-256 으로 봉인하는 무결성 씰**이고, 승인 행위의 인증이 아니다. 봉인은 실제로 작동한다(계획이 바뀌거나 사라지면 continuation 이 거부된다). 사용자 승인 자체는 **계획 게이트에서 사람이 하는 일**이지 이 파일이 증명하는 것이 아니다.

## 실행 3단 (공통 — 산출물 종류로 갈리지 않는다)

> 2026-07-23 재조립 C10: 산출물 타입별 절차 본문은 삭제됐다. 세 단계는 **어떤 작업이든 같다.**

- **step 설계** — plan doc 의 leaf 에 구현 세부만 보충한다. scaffold 를 **재해석하지 않는다**(범위가 바뀌면 그건 재승인 대상).
- **파일 생성 (produce 잔여)** — 계획·스캐폴드·문서만 쓴다. 구현코드·커밋은 아래 실행 단계 전 금지.
- **실행** — 실제로 만들고, **표면에 맞는 실구동으로 검증하고**(웹=브라우저 · CLI=실행+exit code · API=실요청 · 데이터=1회 구동), 커밋한다. git 은 이 구간만 소유한다.

step 을 끝낼 때마다 plan doc 의 `- [ ]`→`- [x]` 를 그 자리에서 켠다 — **체크박스가 진행의 쓰기 정본**이다(장부 권위). `.harness/work.json` 은 거기서 파생되는 이어받기 포인터일 뿐, 어긋나면 plan 이 이긴다. **증거 없는 체크 금지 (2026-07-31 kit 이식)**: 그 step 의 증거(파일·커밋·검증 출력)를 지금 인용할 수 있을 때만 켠다 — 못 하면 되돌린다.

## 무중단 규칙 (intra-milestone no-stop)

- step 완료는 evidence/commit checkpoint일 뿐 turn/run 종료 조건이 아니다. 승인된 plan에 unchecked step이 남아 있으면 다음 leaf를 즉시 시작한다.
- `blocked/error`, 새 사용자 소유 결정·secret·risk, 사용자 명시 중단 외에는 final 응답을 보내지 않는다. 도구 시간이나 컨텍스트 압박은 `PreCompact`/continuation state로 넘기며 임의의 step 경계 종료 사유로 삼지 않는다.
- **구현 중 새 사용자 소유 결정 발견 = 설계 실패로 계수**: `python "$HARNESS_SCRIPTS/ledger_append.py" interruption --reason decision_required`. (계획 단계에서 소진했어야 할 결정이다 — 기록이 다음 계획을 단단하게 만든다.)
- milestone 의 DoD 가 충족되는 완료 경계에 닿으면 멈추지 말고 `/harness-done` 을 로드해 완료 hook 을 돈다.

## 막힘 사다리 (bounded escalation — C8·P6 2026-07-23)

막혔다고 바로 사용자를 부르지 않는다. **멈춤 = 판단 불능**(아키텍처 불일치 · 스펙 위반 의심 · 모호한 작업 · 해결 불가 충돌 · 취향 판단)이고, **되돌릴 수 없음(`위험`)은 멈춤 사유가 아니다** — 그건 계획서 `Risk` 필드가 정한 격리·독립 검증으로 처리한다(C2). 파괴 행위는 제3의 레인 — guard 가 그냥 막는다(알림 없음).

| 단 | 동작 |
|---|---|
| **1** | **빠진 컨텍스트를 주입해 재시도** — 계획서·spec·이전 결정에서 놓친 것을 찾아 같은 leaf 재시도 |
| **2** | **더 센 모델로 재시도** — 같은 leaf 를 상위 모델 서브에이전트로 위임(자기 런타임의 서브에이전트 규약을 따른다 — model 명시 필수). 서브에이전트는 사용자에게 직접 묻지 않는다 — 오케스트레이터만 중계 |
| **3** | **정지 → 사용자에게 평문 질문** — 지금까지 모은 근거와 함께 한 문장으로 묻고 답을 기다린다 |


## 커밋·푸시

**커밋·푸시 기본 (2026-07-17 사용자 확정)** — 승인된 plan/changeset 실행에서 **커밋과 origin push 는 완료 절차의 일부다 — "푸시할까요?" 류 질문으로 정지하지 않는다.** 승인 1회에 push 까지 포함된 것으로 본다. 예외(이때만 정지·확인): ① force-push 등 리모트 파괴 조작(guard 규약 — 사용자 `!` 직접 실행 경로) ② 신규 공개 리포 생성·가시성 변경 ③ 사용자가 "커밋만"·"푸시 보류" 명시 ④ 리모트 없는 레포(로컬 커밋으로 종료·보고).

**add 범위 — 공유 레포에서는 경로를 명시한다 (2026-07-21)** — 여러 에이전트가 같은 레포에서 동시에 일할 수 있는 곳(여러 세션이 함께 쓰는 레포)에서는 `git add -A`·`git add .` 를 쓰지 않고 **이번 작업이 바꾼 경로만 나열해 add** 한다. 커밋 직전 `git status --short` 로 스테이지 밖 변경이 남는지 확인하고, **내 작업이 아닌 변경이 보이면 담지 말고 그대로 둔다**(남의 세션 소유일 수 있다 — 지우거나 stash 하지 않는다). 커밋은 변경 직후 바로 해서 작업 트리에 머무는 시간을 줄인다. 단독 레포·워크트리에서는 해당 없음.

## 재개 프로토콜 (RL1)

문서화된 정지의 재개 = **판정 1개 + 커맨드 1개**: ① blocker 가 실제 해소됐는지 근거 확인(기계가 대신 못 함 — 근거 없으면 재개 금지) ② `python ~/.codex/hooks/harness_work_state.py resume --root . --work-id <id> --session <runtime>:<uuid>` (문서화된 정지 잔존 시 거부, 우회 불가). `stop_detail` 은 사용자가 읽는 한 문장으로(경로·내부 ID 금지 — 알림에 그대로 나감).

## 턴 종료 위치 보고 (plan visibility, U-1)

멀티스텝 milestone 작업 중 턴을 마칠 때(정지·보고·질문 어느 경우든), **계획 위치 블록**(북극성 한 줄 → Milestone(완료 x/y) → 다음 이어갈 leaf)의 노출처는 환경별로 나뉜다 — 두 경로가 동시에 맡으면 화면에 같은 블록이 두 번 나온다(2026-07-14 실관측):
- **전역 Stop hook(`plan_position_stop.py`)이 배포된 환경(Claude)**: 모델은 이 블록을 최종 메시지에 직접 출력하지 않는다 — hook 이 유일한 노출처.
- **그 hook 이 없는 환경(Codex 등)**: 모델이 최종 메시지 끝에 이 블록을 직접 포함한다.
단일 step·계획서 없는 레포는 (환경 무관) 생략.

## 에러 복구

- **error**: 사용자가 해당 status 를 `pending` 으로 되돌리고 error/blocked 메시지 삭제 후 재실행
- **blocked**: 사유 해결 후 동일 (재개는 위 RL1)
