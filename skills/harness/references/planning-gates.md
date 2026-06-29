> harness 셋업·기획 게이트 본문 (lazy-split). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤, SKILL.md 의 §A2/§B0/§B0.5 **stub 이 가리키는 트리거 조건이 성립할 때** 이 파일을 읽고 해당 절차를 따른다. 트리거 조건 자체는 SKILL.md stub 에 있다(언제 읽을지). 여기엔 *무엇을 하는지* 만 있다.

## §A2. Legacy ROADMAP normalization gate

`ROADMAP.md` 에 unchecked 항목(`- [ ]`, `Status: [ ]`)이나 명백한 미완료 섹션은 있지만 `<!-- harness:milestone ... -->` marker 가 없거나 active marker 가 0개면 legacy ROADMAP 으로 판정한다. 이 경우 체크리스트를 곧바로 실행 대상으로 해석하지 않는다. marker 없는 checkbox 는 **milestone 후보**일 뿐이다.

규칙:
- 먼저 `roadmap_sync.py status` 와 `roadmap_sync.py horizon-check --gap-out docs/roadmap-gap-<YYYY-MM-DD>.md` 로 marker 상태를 확인한다.
- legacy 후보를 `ROADMAP.md` 에서 추출해 사용자에게 제안한다. 후보마다 임시 id, 제목, 왜 필요한지(`Gap`), 완료판정(`DoD`), 증거 경로(`Evidence`), 추천 priority 를 붙인다.
- 우선순위는 사용자 요청과 북극성/Current Horizon 에 맞는 항목, 이미 진행 중인 갈래별 status machine 과 연결되는 항목, 증거를 가장 작게 만들 수 있는 항목 순으로 둔다.
- 사용자 승인 전 `ROADMAP.md` 를 marker 형식으로 정규화하지 않는다. 승인 전에는 구현·작성·커밋도 금지한다.
- 승인 후에만 legacy 후보 중 선택된 1~3개를 `## Active Milestones` 아래 `harness:milestone` marker block 으로 승격하고, 나머지는 `## Next Candidates` 로 남긴다.
- 승격하는 block 은 반드시 `DoD`, `Evidence`, `Gap`, `Status: [ ]` 를 포함한다. 이 네 항목이 없으면 `/harness` 완료 sync 대상이 아니다.
- ROADMAP 이 150줄을 넘으면 완료·보류 이력부터 `BACKLOG.md` 로 압축한 뒤 active/pending 후보를 보존한다.

## §B0. Spec readiness gate (정체성·결정 채우기) ★

> **레포 정체성·PRD·TRD·핵심 결정을 채우는 단계의 소유자는 `/harness` 다.** `/harness-bootstrap` 은 *빈 스켈레톤*만 만들고 끝낸다(채우지 않음). harness §A 는 그 문서를 *읽기만* 한다. 그 사이 "무엇을 만들지·어떤 스택·어떤 디자인을 쓸지 사용자와 합의하고 적는" 단계가 무주공산이었다 — 이 게이트가 그 자리다. **step 설계(§C)·구현(§E) 보다 먼저** 돈다.

**언제 발화하나** — §B1 의 non-trivial 기준에 해당하는 작업(특히 product 의 새 기능/제품 구현)일 때. 가볍게 처리 가능(typo·marker·기계적 이어가기)이면 발화하지 않는다. 이미 정체성 문서가 충실히 채워져 있고 이번 작업에 미해결 사용자 결정이 없으면 통과한다.

**1) 정체성 파일 점검** — 갈래별로 아래를 본다:

| 갈래 | 정체성 파일 (채워져야 §C 진입) |
|------|------|
| product | `CLAUDE.md`(기술스택·작업방식 섹션) + `docs/PRD.md` + `docs/ARCHITECTURE.md` + (web 이면) `DESIGN.md` |
| workflow | `CLAUDE.md` + `docs/DOMAIN.md`(법규·기준일·정의) + `config/sources.md` |
| learning | `CLAUDE.md` + `docs/00-INDEX.md`(또는 학습 방향 문서) |
| tooling | `CLAUDE.md`(source-of-truth·deploy 계약 포함) |

각 파일의 상태를 셋으로 판정한다:
- **없음** → 2)로(스캐폴드 후 채움)
- **비었음/스켈레톤** (bootstrap 템플릿 placeholder 가 그대로거나 핵심 섹션이 빈 칸) → 3)으로(채움)
- **채워짐** → 미해결 사용자 결정만 확인 후 통과

**2) 없으면 스캐폴드 (전환 경로 포함)** — 정체성 파일이 없으면(예: learning 으로 부팅한 레포에서 처음 product 작업을 시작), **재부팅·수동 migration 없이** bootstrap 의 additive 재실행으로 그 갈래 정체성 문서만 깐다:

```bash
# product 정체성 문서 추가 (기존 파일 보존, manifest.modes_enabled 에 product 누적)
bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh "$PWD" --full --mode product --kind <web|backend|mobile>
```

이때 `.harness/manifest.json` 의 `primary_mode` 는 자동으로 바꾸지 않는다(사용자가 명시적으로 전환을 원할 때만). `modes_enabled` 에 새 capability 가 누적되는 것으로 전환을 표현한다. → 깐 뒤 3)으로.

**3) ★채우기 — 두 beat** (이게 "어떤 스택·디자인으로 갈지 사용자와 이야기하는" 단계):

- **§B0-1. 논의 (대화 루프, form 아님)**:
  1. 결정 거리를 목록화한다 — product 예: **백엔드**(supabase/firebase/자체 등) · **인증/로그인**(넣을지·방식) · **디자인 방향**(접근·도구) · **스코프**(MVP 경계) · **외부 연동**(결제·API). workflow 예: 기준일·권위 출처·산출 형식.
  2. 각 결정에 **[선택지 + 내 추천 + 근거]** 를 제시한다. 필요하면 조사(WebSearch·레퍼런스)로 근거를 보강한다.
  3. 사용자와 왕복하며 좁힌다. **한 방이 아니라 결정이 다 매듭질 때까지 도는 루프.** 매듭은 Claude 에서 AskUserQuestion 으로 찍는다(Codex 면 평문 한 줄). AskUserQuestion 은 *대화의 결론을 박제하는 도구*이지 대화 자체를 대체하지 않는다.
     - **1차 답이 2차 결정을 부른다 — 그 cascade 도 같은 루프에서 매듭짓는다.** 1라운드에서 멈추지 마라. 예: "진짜 지도" → *어느 제공자(Kakao/Naver)·길찾기 vs 보간*; "백엔드 둠" → *인증 모델·스키마·데이터 위치*; "결제 넣음" → *PG·정산*. 1차 선택이 열어젖힌 후속 갈림길을 surface 해 추가 라운드로 닫는다.
  4. 사용자 소유 결정(스택·인증·결제·디자인 언어·스코프·외부연동)은 추정 진행 금지 — 반드시 사용자 확정. AI 가 합리적으로 기본값 잡아도 되는 것(파일 배치·코드 스타일)만 진행.
- **§B0-2. 기록**:
  - 확정된 내용을 `docs/PRD.md`(무엇을·왜·핵심기능·스코프) + `docs/ARCHITECTURE.md`(구조·기술스택) + `CLAUDE.md`(§ 기술 스택/작업 방식) 에 적는다.
  - **결정 1개 = ADR 1개** — "왜 supabase 인가" 같은 선택은 `docs/adr/000N-<title>.md` 로 근거와 함께 박는다.
  - **외부 크레덴셜이 필요한 결정은 "BLOCKED until 발급" 으로 명시한다** — 결정이 API 키·OAuth·DB URL 등 사용자가 발급해야 하는 시크릿을 요구하면(예: Kakao JS 키·Supabase URL/anon key), PRD/ADR 에 필요한 크레덴셜 목록과 함께 박고, 그 키에 의존하는 §C/§E step 은 키 발급 전까지 `blocked`(§E-6) 으로 둔다. 시크릿 실값은 절대 spec·커밋에 넣지 않는다(env 만).
  - spec 채우기는 구현과 분리된 커밋으로 남긴다: `git commit -m "docs(spec): <기능> 정체성·결정 확정"`.

**4) 게이트** — 위 1~3 이 끝나기 전엔 §C(step 설계)·§E(구현)로 넘어가지 않는다. 채우는 게 먼저, 다 채운 뒤 설계로 진행. 단 이미 채워져 있고 미해결 결정이 없으면 이 게이트는 한 줄 통과("spec 충분 — §C 진입")만 남기고 지나간다.

> 전체 비트: **논의(결정) §B0-1 → 기록(PRD/ADR) §B0-2 → 설계(step) §C → 실행 §E.** ROADMAP 의 "다음 후보를 active 로 승격" 도 사용자 소유 결정이므로, active milestone 이 비어 새 방향이 필요하면 이 게이트에서 함께 합의한다(§A1·§B3 연계).

## §B0.5. Planning cascade authoring (Objective→Horizon→Milestone 작성) ★

> cascade plan docs(ADR 0007)를 *읽는* 건 §A 공통, *짜는* 건 여기다. §B0(Spec readiness)이 제품 정체성·PRD·결정을 채운다면, §B0.5 는 그 위 **기획 위계(Objective/Horizon/Milestone)를 단계적으로 작성**한다. §A1(active=0)·§A2(legacy)·§B2 필수정지·§B3(완료 후 active=0) 의 "새 objective/horizon/milestone 이 필요" 분기가 이리로 라우팅된다. cascade 가 없는 레포는 이 beat 를 건너뛰고 ROADMAP-only 로 동작(optional, 점진 도입).

**언제 발화하나 (planning 갭 감지)** — 아래 중 하나면 그 beat 부터:
- `docs/OBJECTIVE.md` 없음/스켈레톤 → **Beat 1(Objective)**
- active milestone = 0 + 사용자가 새 방향/horizon 을 원함 → **Beat 2(Horizon)**
- active horizon 에 새 milestone 이 필요 → **Beat 3(Milestone)**
가볍게 처리 가능(기존 milestone 이어가기·이미 있는 후보 승격만·typo)이면 발화하지 않는다. 이미 있는 pending/Next Candidate 를 그대로 active 로 올리는 건 §B3 continuation(작성 아님).

**원칙** — 각 beat 는 §B0-1 식 **대화 루프**다: 결정 거리를 [선택지 + 추천 + 근거]로 제시 → 왕복하며 좁힘 → Claude 는 AskUserQuestion, Codex 는 평문 한 줄로 매듭. 사용자 소유 결정(방향·우선순위·범위·무엇을 담나)은 추정 진행 금지. **1차 답이 부르는 cascade(horizon 정하면 첫 milestone 후보, milestone 정하면 step 경계)도 같은 루프에서 매듭.** 작성은 `templates/` 기반, 작성물은 구현과 분리된 `docs(spec):` 커밋.

**Beat 1 — Objective** (`docs/OBJECTIVE.md` 없을 때만):
1. 북극성(`CLAUDE.md`)에서 출발 → **성공 모습**(관측 가능한 최종 상태)·**움직이는 축**(현재→목표 위치·측정법)·**긴 arc**(지나온·갈 phase)를 사용자와 합의.
2. `templates/OBJECTIVE_TEMPLATE.md` 로 작성. 거의 안 변하는 단수 문서 — active horizon 으로 링크.

**Beat 2 — Horizon** (active milestone = 0 / 새 horizon):
1. 직전 phase 가 드러낸 갭에서 **"왜 지금"** 을 도출(`horizon-check` gap report 활용 가능).
2. **horizon 목표** + **담을 milestone 후보(2~5)** + **닫는 기준** 합의.
3. `templates/HORIZON_TEMPLATE.md` 로 `docs/horizons/<slug>.md` 작성 + `ROADMAP.md` `harness:goal` 줄을 그 doc 포인터로 갱신.

**Beat 3 — Milestone** (horizon 의 다음 milestone):
1. 후보 1개 선택 → **DoD**(통합 증거)·**Evidence**(파일/커맨드 경로)·**Gap**(왜 필요) 합의.
2. **§A1 step-leaf 루브릭으로 규모 확인** — milestone-grade(≥2 독립 step/changeset + 통합검증)일 때만 milestone. step-grade 면 milestone 만들지 말고 갈래 status machine 에만 기록(milestone 인플레 금지).
3. `ROADMAP.md` `harness:milestone` marker(status="active") 작성 + **§B2-scope 로 step 트리**를 `docs/plans/<date>-<slug>.md` 에 펼친다(plan doc 위계 섹션은 Objective/horizon 백링크).

**게이트** — 작성한 cascade 문서(들)를 `docs(spec):` 커밋으로 남긴 뒤 **§A1(active milestone 선택) → §B2(produce/run) → §E(실행)** 로 흐른다. 사용자 결정 확정 전 §E 진입·구현·커밋 금지. 한 호출에서 여러 레벨을 새로 작성했으면(예: Objective+Horizon+Milestone 동시) 각 레벨 작성을 같은 spec 커밋에 묶어도 된다.

## §B3 참조 — ROADMAP marker 형식 + roadmap_sync helper

> SKILL.md §B3(lifecycle 규칙·완료 hook)에서 가리키는 reference. marker 를 *작성*할 때(§B0.5 Beat 2/3) 이 형식을 쓰고, 완료/압축 시 helper 를 호출한다.

`ROADMAP.md` 표준 marker:
```markdown
# ROADMAP

> 마지막 업데이트: YYYY-MM-DD
> 상태: <current horizon>
> 북극성: <CLAUDE.md 의 궁극 목표 한 줄>
> line budget: <=150

## Current Horizon

<!-- harness:goal id="evidence-phase" -->
목표: <이번 horizon 의 목표> (상세 plan → `docs/horizons/<slug>.md`)

## Active Milestones

<!-- harness:milestone id="E2" status="active" priority="P0" -->
### E2 — dogfooding 깊이
- DoD: <완료 판정 기준>
- Evidence: <파일/커맨드/로그>
- Gap: <왜 필요한가>
- Status: [ ]

## Next Candidates
- <아직 active 는 아닌 후보>

## Archive Pointer
완료 이력은 `BACKLOG.md` 참조.
```

공통 helper:
```bash
HARNESS_SCRIPTS="$HOME/.codex/skills/harness/scripts"
[ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness/scripts"

python "$HARNESS_SCRIPTS/roadmap_sync.py" status
python "$HARNESS_SCRIPTS/roadmap_sync.py" complete --milestone <ID> --evidence <path-or-command> --summary "<한 줄 결과>"
python "$HARNESS_SCRIPTS/roadmap_sync.py" compact --max-lines 150 --backlog BACKLOG.md
python "$HARNESS_SCRIPTS/roadmap_sync.py" horizon-check --gap-out docs/roadmap-gap-<YYYY-MM-DD>.md
```

## §B3-continuation — Continuation opt-in 상세

> SKILL.md §B3 Continuation opt-in stub 이 가리키는 reference. stub 에 spine(언제·1개만 승격·§A1 재시작)은 있고, 여기엔 승격 가능 조건·선택 규칙·정지 조건의 *판정 기준*이 있다.

승격 가능 조건:
- `ROADMAP.md` 에 `status="pending"` 인 후보 또는 `## Next Candidates` 후보가 이미 있다.
- 후보 block 에 `DoD`, `Evidence`, `Gap`, `Status: [ ]` 가 있다.
- 후보가 §A1 Product milestone grain check 를 통과한다.
- 새 사용자 결정, secret 발급, 외부 콘솔 작업, risk gate, blocker 가 필요하지 않다.
- `blocked`/`error` 상태가 아니고, `ROADMAP.md` line budget 을 지킬 수 있다.

선택 규칙:
- 후보가 1개면 그 후보를 active 로 승격한다.
- 후보가 여러 개면 priority(P0→P1→P2), 사용자 요청과의 정합성, blocker 없음, evidence 를 가장 작게 만들 수 있는 순서로 1개를 고른다.
- 사용자가 "가능한 만큼 계속" 이라고 명시하지 않았으면 한 번의 continuation 요청으로 최대 1개 milestone 만 추가 실행한다. 여러 milestone 을 연속 처리할 때도 각 완료마다 gate 를 다시 평가한다.

정지 조건:
- 승격할 후보가 없거나 후보가 불완전하면 `horizon-check` gap report 를 만들고 멈춘다.
- 새 horizon/milestone 을 작성해야 하면 사용자 승인 전 멈춘다(작성은 §B0.5).
- continuation 으로 승격했다면 `ROADMAP.md` 변경을 먼저 커밋하거나, 구현 커밋과 분리해 결과 보고에 명확히 남긴다.

## §B3-완료hook — Milestone 완료 hook 상세

> SKILL.md §B3 Milestone 완료 hook stub 이 가리키는 reference. stub 에 spine(gate PASS→DoD확인→complete→compact→horizon-check)은 있고, 여기엔 각 단계의 *판정 기준·정지 조건*이 있다.

1. 갈래별 gate 가 PASS 한다(product AC, learning 5/5 또는 experiment 4/4, tooling targeted test/smoke/sync evidence PASS, workflow-B `verify-run.py` PASS).
2. 해당 작업이 `ROADMAP.md` 의 milestone `DoD` 를 만족하는지 evidence path 로 확인한다.
3. 만족하면 `roadmap_sync.py complete ...` 로 marker `status="completed"` + `Status: [x]` + evidence/summary 를 기록한다.
4. `roadmap_sync.py compact --max-lines 150` 실행. 완료 block 이 많으면 `BACKLOG.md` 로 이동한다.
5. `roadmap_sync.py horizon-check ...` 실행. active milestone 0개면 기본적으로 **새 구현으로 넘어가지 말고 멈춘다**. 생성된 gap report 에 north star / current state / gap / proposed next horizon 을 적고 사용자 승인 전 `ROADMAP.md` 에 새 horizon 을 쓰지 않는다. 사용자가 새 방향을 승인하면 **§B0.5 Planning cascade authoring** 으로 들어가 Objective(필요시)→Horizon→Milestone 을 토론 루프로 작성한다.
6. 예외: 이번 turn 에 사용자가 명시적으로 continuation 을 요청했고 `§B3-continuation` 조건을 통과하면 pending/Next Candidate 1개를 active 로 승격하고 §A1 부터 다시 시작한다. continuation 은 자동 루프가 아니며, "가능한 만큼 계속" 지시가 없으면 1개 milestone 실행 후 다시 boundary 에서 멈춘다.
