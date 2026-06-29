---
name: harness
description: >-
  jha0313/harness_framework 기반 구조적 구현 워크플로우를 갈래 4분기(product/learning/tooling/workflow)로 확장 — harness-bootstrap(설치)이 끝난 프로젝트에서 실제 작업 실행 시 사용. §0 갈래 자동 감지(갈래 본문 §C~§E 는 references/<branch>.md 에서 on-demand 로드) 후 product=phases/+step 파일 순차 실행, learning=reference 분석(ANALYSIS 5섹션)+인덱스 표, tooling=스킬·스크립트·런타임 changeset+검증, workflow=playbook 작성/실행. §A1 위계·스케일 루브릭(관측 가능한 step-leaf 테스트)으로 horizon/milestone/step 규모를 가르고, 긴 작업은 §E 실행 전에 §B2-scope 재귀 분해로 durable plan doc(docs/plans/)에 step 트리를 펼쳐 Claude/Codex 가 몇 시간 이어가게 한다. active milestone 이 없거나 새 방향이 필요하면 §B0.5 Planning cascade authoring 으로 Objective→Horizon→Milestone 을 토론 루프로 작성(docs/OBJECTIVE.md·docs/horizons/)한다. 가드레일 주입·컨텍스트 누적·3회 자가교정·2단계 커밋. 사용자가 "/harness", "하네스로 개발해줘", "단계별로 나눠서 구현", "step 파일 만들어줘", "phases 생성해줘", "레퍼런스 분석해줘", "reference 분석 노트", "스킬 수정", "tooling changeset", "playbook 작성", "playbook 실행", "멀티스텝 개발 계획", "step으로 쪼개서 설계", "계획 세워서 문서화", "설계도 만들어줘", "어디까지 구현할지 정하고 진행", "objective 짜줘", "horizon 정해줘", "프로젝트 목표/방향 잡아줘", "새 horizon 기획", "마일스톤 계획" 이라고 말할 때 반드시 이 스킬을 사용하라. 단순 계획만 원하면 /spec을, 신규 레포 초기 세팅이면 /harness-bootstrap을 사용.
---

이 프로젝트는 harness-bootstrap 으로 부팅된 하네스를 쓴다. 아래 워크플로우에 따라 작업하라.

원본: jha0313/harness_framework 의 `/harness` 명령을 갈래 4분기(product/learning/tooling/workflow)로 확장. execute.py 자리는 **기본적으로** Claude Code 자신이 대체 (인라인 실행 = 외부 subprocess 없음). 원본 엔진은 product 무인자동화용 *옵션*으로 `scripts/execute.py` 에 보존 — 아래 박스 참조.

> **실행 엔진 (product 갈래 선택)**: 이 스킬엔 `scripts/execute.py`(jha0313 원본 엔진 — 가드레일 주입·컨텍스트 누적·3회 retry·2단계 커밋·브랜치 관리)가 번들돼 있다. 기본은 **인라인 실행**(위 한 줄)이고, product 갈래에서 *무인 순차 자동화*를 원할 때만 엔진을 쓴다. learning/workflow 는 엔진 안 씀.
>
> Codex 에서는 `~/.claude/...` 경로를 하드코딩하지 않는다. Codex 배포본은 `~/.codex/skills/harness/scripts/` 에 있을 수 있고, Claude 배포본은 `~/.claude/skills/harness/scripts/` 에 있을 수 있다. 예:
> ```bash
> HARNESS_SCRIPTS="$HOME/.codex/skills/harness/scripts"
> [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness/scripts"
> python "$HARNESS_SCRIPTS/execute.py" <task>
> ```

**핵심: 갈래마다 status machine 의 grain 자체가 다르다.** Product 만 `phases/` 를 쓰고, Learning/Tooling/Workflow 는 각자의 인덱스 또는 실행 파일이 status 역할.

---

## §0. 갈래 감지 (조용히, 사용자에게 묻기 전)

**중요: 갈래는 "레포의 영구 정체성"이 아니라 이번 `/harness` run 의 실행 모드다.** `/harness-bootstrap` 재실행은 기존 파일을 지우지 않고 새 갈래 파일을 *추가*하므로, 파일 존재만으로 전체 레포 모드를 고르면 시간이 지나며 오판한다.

판정 순서:
1. **명시적 사용자 의도**가 있으면 우선한다.
   - `playbook 실행`, `run.json`, `outputs/`, `workflow-B` → workflow-B
   - `playbook 작성`, `PLAYBOOK_TEMPLATE`, `workflow-A` → workflow-A
   - `reference 분석`, `ANALYSIS`, `레퍼런스`, `experiment`, `실험` → learning
   - `스킬 수정`, `SKILL.md`, `setup.sh`, `skill-trigger-acceptance`, `hardening parity`, `runtime`, `tooling`, `changeset` → tooling
   - `phases`, `step 파일`, `product 구현`, `PRD/API/UI` → product
2. `.harness/manifest.json` 이 있으면 읽는다. `primary_mode` 는 최초/주 정체성, `modes_enabled` 는 추가 부팅된 실행 능력이다. **manifest 만으로 이번 mode 를 확정하지 말고**, 사용자 의도·ROADMAP target 과 대조한다.
3. `ROADMAP.md` 의 active milestone 이 특정 갈래 산출물을 가리키면 그 갈래를 선택한다.
   - `phases/...`, `docs/PRD.md`, `docs/ARCHITECTURE.md` → product
   - `references/.../ANALYSIS.md`, `experiments/...` → learning
   - `changesets/...`, `skills/.../SKILL.md`, `scripts/...`, `setup.sh` → tooling
   - `playbooks/...`, `outputs/.../run.json`, `config/sources.md` → workflow
4. 위가 불충분할 때만 파일 signature 를 **capability** 로 해석한다.
   - workflow capability: `docs/DOMAIN.md` + `playbooks/`
   - tooling capability: `changesets/`
   - learning capability: `references/` 또는 `experiments/`
   - product capability: `docs/PRD.md` 또는 `docs/ARCHITECTURE.md`
5. 가능한 갈래가 1개면 선택한다. 2개 이상이면 추정 진행하지 말고 "이번 `/harness` run 은 product / learning / tooling / workflow-A / workflow-B 중 무엇으로 진행할지" 를 사용자에게 한 줄로 묻는다.

구형 레포에는 `.harness/manifest.json` 이 없을 수 있다. 이 경우 위 1→3→4 순서로 판정하되, 여러 capability 가 공존하면 다중 갈래 레포로 보고 사용자 확인 또는 ROADMAP normalization 으로 들어간다.

다음 흐름이 갈래마다 달라진다.

**Workflow 면 추가 모드 선택 필수**:
- **작성** (Workflow-A): 새 playbook 신규 작성 (1회성)
- **실행** (Workflow-B): 기존 playbook 1회 적용 (반복) ★ 가장 다른 흐름

---

## §A. 탐색 (공통, 갈래별 컨텍스트 목차)

갈래별 우선 읽을 파일:

| 갈래 | 필수 읽기 |
|------|---------|
| product | `ROADMAP.md` (백로그·다음 할 일) + `docs/PRD.md` + `docs/ARCHITECTURE.md` + (web이면) 루트 `DESIGN.md` / (mobile이면) `docs/UI_GUIDE.md` + `docs/adr/` |
| learning | `ROADMAP.md` + `docs/00-INDEX.md` + 관련 `references/*/ANALYSIS.md` |
| tooling | `ROADMAP.md` + `CLAUDE.md` + 관련 `changesets/*/README.md` + 영향받는 `SKILL.md`/script/test/deploy 문서 |
| workflow-A | `ROADMAP.md` (백로그·다음 할 일) + `docs/DOMAIN.md` + `config/sources.md` + 유사 `playbooks/*.md` (있으면) |
| workflow-B | `ROADMAP.md` + 실행할 `playbooks/<task>.md` + `docs/DOMAIN.md` + `config/sources.md` |

**공통 cascade (있으면 위→아래로 읽어 이어받기, ADR 0007)**: `docs/OBJECTIVE.md`(북극성 확장) → 현 `ROADMAP.md` `harness:goal` 가 가리키는 `docs/horizons/<slug>.md`(active horizon plan) → 그 milestone 의 `docs/plans/<date>-<slug>.md`. 새 에이전트는 이 cascade 를 읽고 작업을 이어간다. cascade docs 가 없는 레포는 `ROADMAP.md` 만으로 진행(optional).

**공통 — 반드시 읽고 위반 금지**: `CLAUDE.md` 의 `## ⚠ Judge 규약` 줄.

필요시 Explore 에이전트 병렬.

### §A1. Active milestone selection

`ROADMAP.md` 를 읽은 뒤 이번 `/harness` run 이 전진시키거나 닫을 **target milestone** 을 확정한다. 이 단계는 갈래별 status machine 을 실행하기 전의 상위 정합성 확인이다.

규칙:
- 여기서 active milestone 은 marker 가 `status="active"` 인 milestone 만 뜻한다. `pending`/`blocked`/`error` 는 open 이지만 runnable active 로 세지 않는다.
- active milestone 이 1개면 기본 target 으로 선택한다. 단 해당 block 에 `Blocked by:` 가 있거나 상태/본문상 blocked·error 가 남아 있으면 진행하지 말고 blocker 해소를 먼저 사용자에게 제시한다.
- active milestone 이 여러 개면 `priority`, 사용자 요청, blocker 여부, 갈래별 status machine 의 다음 pending 작업을 대조해 1개를 선택한다.
- 선택한 milestone 의 `DoD`, `Evidence`, `Gap` 을 이번 run 의 planning context 와 step/playbook/checklist 설계에 반영한다.
- 사용자 요청이 어떤 active milestone 과도 정합하지 않을 때: **먼저 그 작업이 milestone-grade 인지 step-grade 인지 §A1 루브릭으로 판정한다.** step-grade(step-leaf=leaf, 보통 단일 tooling changeset·1 ref·좁은 수정)면 **새 ROADMAP milestone 을 만들지 말고** 기존 milestone 의 `Gap` 채우기 또는 *maintenance* 로 보고 갈래 status machine(changeset 표 등)에만 기록한다 — milestone 제조 금지(milestone 인플레). milestone-grade(≥2 독립 step/changeset + 통합 검증 + 단독 capability)일 때만 §B1 `planning_gate.spec_delta` 로 새 milestone 을 제안한다.
- active milestone 이 0개면 기본적으로 새 구현으로 들어가지 말고 `roadmap_sync.py horizon-check --gap-out docs/roadmap-gap-<YYYY-MM-DD>.md` 를 실행해 gap report 를 만든 뒤 멈춘다. 단 사용자가 이번 메시지에서 "이어가", "계속", "다음 후보 active로 올려", "run next", "가능한 만큼 계속" 처럼 명시적으로 continuation 을 요청했고 §B3 continuation gate 를 통과하면, pending/Next Candidate 1개를 active 로 승격한 뒤 §A1 을 다시 시작할 수 있다. **이미 있는 후보 승격이 아니라 새 horizon/milestone 을 *작성*해야 하면(사용자가 새 방향을 원함) §B0.5 Planning cascade authoring 으로 들어간다.**
- 정합성 판단이 애매하면 추정으로 진행하지 말고 "이번 작업을 어느 ROADMAP milestone 에 연결할지" 를 사용자에게 한 줄로 묻는다.

#### 위계·스케일 루브릭 (공통 — 모든 갈래)

북극성 → horizon → milestone → step 으로 *재귀 분해*한다. 규모는 **시간이 아니라 관측 가능한 테스트**로 가른다 — 시간 추정("수 시간짜리")은 모델이 측정 못 해 호출마다 달라지지만, "검증 하나로 닫히냐 / 사용자 결정이 끼냐 / surface 가 몇 개냐"는 일관되게 판단된다. 핵심은 **step-leaf 테스트** = "그만 쪼개라"의 정지 조건:

| 레이어 | 판정 테스트 (관측 가능) | status 위치 |
|------|---------|-----------|
| **step (leaf)** | ① 한 coding pass 로 닫힌다 ② 단일 커맨드·체크 하나로 검증된다 ③ 한 레이어·모듈·파일셋만 건드린다 ④ 새 사용자 결정이 필요 없다 — **4개 다 충족 → leaf, 더 안 쪼갠다** | 갈래별 status machine (`phases/stepN.md`/changeset/ref row) |
| **milestone** | step 이 ≥2개 필요 + 그 step 들을 가로지르는 통합 검증이 ≥1개 + 단독 capability·증거로 설명됨 (+ 사용자 결정을 부를 수 있음) → step 으로 쪼갠다 | ROADMAP `harness:milestone` (DoD/Evidence/Gap) |
| **horizon** | milestone 여럿을 담고 북극성을 향한 1개 측정가능 phase → milestone 으로 쪼갠다 | ROADMAP `harness:goal`, active 1개 |

판정: step-leaf 테스트를 **위에서 아래로** 적용해, 통과 못 하는 노드는 한 단계 더 쪼갠다(이 절차가 §B2-scope 의 재귀 분해). milestone DoD=통합 증거, step AC=구체 커맨드/파일 검증. 아래 Product grain check 는 이 테스트의 product 특화 예시(좁은 화면·컴포넌트 하나=step, 제품 arc=milestone)다. (이 루브릭은 §A1 grain check·§A2 후보 sizing·§B2-scope 재귀 분해·§B3 continuation 의 **공용 정의** — §A1 은 그 홈일 뿐 선택 단계 전용이 아니다.)

#### Product milestone grain check

Product 갈래의 ROADMAP milestone은 단일 구현 task가 아니라 사용자가 체감하는 제품 arc여야 한다.
- 좋은 milestone: `출시 전 서비스 전체 UI 폴리싱`, `운영 배포 안정화`, `리텐션 루프 강화`, `카탈로그 운영성 강화`.
- 너무 작은 milestone: `추적 하단 sheet`, `receipt visual`, `OAuth smoke`, `검색 필터 chip`처럼 한 화면/컴포넌트/좁은 검증 하나로 닫히는 일.
- 한 짧은 coding pass로 닫히고 제품 capability를 단독으로 설명하기 어렵다면 ROADMAP milestone이 아니라 `phases/<task>/stepN.md`로 둔다.
- ROADMAP milestone은 보통 여러 surface 또는 여러 evidence gate를 포함한다. 세부 화면/컴포넌트/스크립트/QA는 phase steps로 쪼갠다.
- 이미 ROADMAP active milestone이 너무 좁으면 구현으로 바로 들어가기 전에 §B1 `planning_gate.spec_delta`로 "broader milestone으로 병합/재편"을 제안한다.
- milestone DoD는 end-to-end 사용자 가치와 통합 evidence를 적고, step AC는 구체 커맨드/파일 단위 검증을 적는다.

### §A2. Legacy ROADMAP normalization gate

**트리거**: `ROADMAP.md` 에 unchecked 항목(`- [ ]`, `Status: [ ]`)·미완료 섹션은 있는데 `<!-- harness:milestone -->` marker 가 없거나 active marker 0개 = **legacy ROADMAP**. 이때 체크리스트를 곧바로 실행 대상으로 보지 말 것(marker 없는 checkbox = milestone 후보일 뿐). → **`references/planning-gates.md` §A2 를 읽고 정규화 절차(roadmap_sync status/horizon-check → 후보 제안 → 사용자 승인 후에만 marker 승격)를 따른다.** 승인 전 정규화·구현·커밋 금지.

---

## §B. 논의 (공통)

구현·작성을 위해 구체화/결정해야 할 사항을 사용자에게 제시하고 합의. Claude 에서 AskUserQuestion 이 가능하면 묶어서 묻는다. Codex 에서는 AskUserQuestion 을 가정하지 말고, 합리적 기본값으로 진행하되 결정 없이는 위험한 경우에만 평문 한 줄 질문으로 묻는다.

### §B0. Spec readiness gate (정체성·결정 채우기) ★

> 레포 정체성·PRD·TRD·핵심 결정을 채우는 단계의 소유자는 `/harness` 다(bootstrap 은 빈 스켈레톤만, §A 는 읽기만). **step 설계(§C)·구현(§E) 보다 먼저** 돈다.

**트리거**: §B1 non-trivial 기준(특히 product 새 기능/제품 구현)인데 정체성 문서 — product=`CLAUDE.md`+`docs/PRD.md`+`docs/ARCHITECTURE.md`(+web `DESIGN.md`) / workflow=`docs/DOMAIN.md`+`config/sources.md` / learning=`docs/00-INDEX.md` / tooling=`CLAUDE.md`(source-of-truth·deploy 계약) — 가 **없음/스켈레톤**이거나 **미해결 사용자 결정**이 있으면 → **`references/planning-gates.md` §B0 을 읽고 절차(스캐폴드 → §B0-1 논의 루프[선택지+추천+근거] → §B0-2 PRD/ADR 기록 → docs(spec) 커밋)를 따른다.** 이미 충실히 채워졌고 미결 결정 없으면 한 줄 통과("spec 충분 — §C 진입"). (§B0-1/§B0-2 라벨의 정의는 그 파일에 있다.)

### §B0.5. Planning cascade authoring (Objective→Horizon→Milestone 작성) ★

> cascade plan docs(ADR 0007)를 *읽는* 건 §A 공통, *짜는* 건 여기. §B0 이 제품 정체성을 채운다면 §B0.5 는 그 위 기획 위계를 작성한다.

**트리거 (planning 갭 감지)** — 아래 중 하나면 → **`references/planning-gates.md` §B0.5 를 읽고 해당 beat 를 따른다**(각 beat 는 §B0-1 식 토론 루프 → `templates/` 작성 → `docs(spec):` 커밋):
- `docs/OBJECTIVE.md` 없음/스켈레톤 → Beat 1(Objective)
- active milestone = 0 + 사용자가 새 방향/horizon 원함 → Beat 2(Horizon)
- active horizon 에 새 milestone 필요 → Beat 3(Milestone; §A1 규모판정으로 milestone-grade 확인)

§A1(active=0)·§A2·§B2 필수정지·§B3(완료 후 active=0) 가 이리로 라우팅. 기존 milestone 이어가기·후보 승격(=§B3 continuation)·typo 면 발화 안 함. cascade 없는 레포는 건너뜀(ROADMAP-only, optional). 작성 후 §A1→§B2→§E 로 흐른다.

### §B1. Thin non-trivial planning gate

가벼운 수정은 바로 진행해도 된다. 하지만 non-trivial 작업을 단순 TODO로 쪼개서 바로 실행하지 않는다.

**non-trivial 기준** — 아래 중 하나라도 해당하면 이 gate를 적용한다:
- 여러 task / 여러 file / 여러 session에 걸친 작업
- product behavior, API, data model, 권한, 결제, 외부 연동, 배포면 변경
- security, secret, supply chain, protected file에 영향
- 기존 spec, ROADMAP, ADR, 과거 판단과 충돌 가능성
- 사용자가 외부 제품/경쟁/사례/개선안을 가져와서 반영 여부 판단이 필요한 경우

**가볍게 처리 가능**:
- typo, format, README/CHANGELOG만 수정
- marker/status 업데이트만 수행
- 기존 spec과 테스트로 정답이 고정된 좁은 버그 수정
- 이미 생성된 step/playbook/checklist의 기계적 이어가기

non-trivial이면 §C 설계 산출물 또는 사용자 보고에 아래 planning block을 포함한다:

```yaml
planning_gate:
  team_validation_mode: not_required_lightweight | native | subagent | manual-pass | unavailable
  spec_delta: "<spec/ADR/ROADMAP에 반영할 변경>"   # 없으면 spec_skip_reason 사용
  spec_skip_reason: "<product contract 갱신을 생략하는 이유>"
  perspectives:
    product: "<사용자 가치/범위 적합성>"
    architecture: "<구조/경계/확장성>"
    security: "<권한/secret/supply-chain 위험>"
    qa: "<test/smoke/CI/DoD>"
    skeptic: "<반대 논리/실패 가능성>"
  dod:
    - "<실행 가능한 검증 또는 evidence artifact>"
```

규칙:
- `spec_delta` 와 `spec_skip_reason` 중 하나는 반드시 적는다.
- `team_validation_mode` 는 도구가 실제로 가능할 때 `native`/`subagent`, 아니면 관점별 자체 검토를 분리해 `manual-pass` 로 둔다.
- `unavailable` 은 임시 상태다. Required 계획으로 확정하지 않는다.
- Security 관점은 secret 실읽기를 요구하지 않는다. `.env` 또는 토큰 확인이 필요하면 Risk Gate 로 멈춘다.
- source code 변경이 있으면 lint / formatter / test / smoke / review gate 중 하나 이상이 DoD에 들어가야 한다.

가벼운 작업은 `team_validation_mode: not_required_lightweight` 로 충분하며, 긴 planning block을 만들지 않아도 된다.

---

## §B2. produce / run 게이트 (공통 — 갈래 무관)

> dryforge produce/run 경계의 일반화. `ready`·`set` 은 문서만 쓰고 `go` 가 git 을 소유하는 그 분리를, 단일 `/harness` 안의 **정지·승인 체크포인트**로 흡수한다.

- **produce = §A 탐색 ~ §D 파일 생성.** 문서·계획·스캐폴드만 쓴다. 실제 구현코드·최종 산출물 생성·작업물 git 커밋 **금지**.
- **run = §E 실행.** 가드레일 주입하에 실제로 만들고·검증하고·커밋한다. git 기계장치는 run 만 소유.

> **§B2 는 produce 구간을 *여닫는 두 시점*을 담는다.** 아래 **§B2-scope = produce *진입* 게이트(§C 전 발화)**, 그 다음 **pass-through 이하 = produce→run *경계* 게이트(§D 후 발화)**. 한 섹션이지만 같은 순간에 다 도는 게 아니다.

**§B2-scope (produce 진입 — §C·§E 전). scope 결정 + 재귀 분해 → plan doc.** milestone 이 여러 step 으로 쪼개지거나 세션을 넘겨 이어받을 작업이면, §C(spec)·§E(실행) 전에:
1. **scope 경계** — 이번 run 이 닫을 범위 + 중단점(검증 PASS·blocked·budget). **결정 지점 지도: §A1=어느 milestone · 여기=이번 run 어디까지 · §B3=다음 후보 승격** (세 facet, 혼동 말 것). scope 가 사용자 소유(어디까지·무엇 제외)면 §B0-1 처럼 묻는다.
2. **재귀 분해 → plan doc** — 목표→milestone→step 으로 §A1 **step-leaf 테스트**를 적용해 leaf 까지 쪼개, 트리를 `docs/plans/<YYYY-MM-DD>-<slug>.md`(product `phases/<task>/PLAN.md`, 템플릿 `templates/PLAN_TEMPLATE.md`)에 **체크박스 트리(한 줄/leaf, spec 인라인 X)** 로 박는다. plan doc 위계 섹션은 cascade 상위(`docs/OBJECTIVE.md`·`docs/horizons/<slug>.md`)로 백링크한다(ADR 0007, §B3). leaf 의 구체 spec(read-files·시그니처·AC)은 §C 엔진이 채운다(트리·spec 비대화는 §E-3 누적 비용↑ — 시그니처 수준 유지). **장부 권위: plan doc = milestone 픽업용 상위 트리(읽기 위주) / 갈래 status machine(`index.json`·changeset 표·`run.json`) = step 실시간 상태(쓰기 *정본*)** — 진행률은 status machine 이 정본, plan doc 체크박스는 milestone boundary 에서만 동기화(이중기록 drift 방지). 이 plan doc 으로 **새 에이전트가 몇 시간 이어받는다.**
3. **아는 만큼만 펼친다** — 전체를 미리 못 펼치는 탐색적 작업은 *지금 아는 다음 1~2 leaf* 만 확정·진행하고 나머지는 finding 큐로 emerge 시킨다. up-front 완전 분해 강요 = 분석마비, 금지.
4. **면제 + 과분해 금지**: 단일 step·가벼운 작업, **learning(1 ref=1 step)·workflow-B(playbook 고정)** 는 평면 — 재귀 면제. **★tooling 기본 단위 = 1 changeset = 1 step.** 한 응집적 변경이면 *파일이 여럿이고 검증 항목이 여럿이어도* 1 step 이다 — **여러 검증 단계 ≠ 여러 step**(검증은 changeset 의 Verification 체크리스트로). 재귀 분해·plan doc·milestone 은 **≥2 *독립* changeset(별개의 응집 변경) + 통합 검증**일 때만. 한 changeset 을 4-leaf 트리로 펴는 건 과분해 — dogfood 에서 적발(F2/T3).
5. **plan doc 게이트 (self-check)** — multi-step milestone 이면 §E 진입 전 plan doc 에 ① step 트리 ≥2 leaf ② 각 leaf 의 AC/검증 한 줄 ③ 중단점 이 있어야 한다. 없으면 §E 진입 말고 이 단계로 복귀 (product `npm test` AC·workflow-B `verify-run.py` 에 대응하는 *분해 완성* 자가 점검 — pass-through 의 "사용자 승인 생략"과 별개로 산출물 완성도는 점검).

**기본은 통과 (pass-through).** §D 끝나면 produce 산출물 경로 + run 이 바꿀 것을 **한 줄 통지**("produce 끝 → run 진입: …")만 하고 §E 로 바로 넘어간다. 매번 멈추지 않는다.

**필수 정지 예외.** §A1 에서 target milestone 이 없거나, 사용자 요청과 active milestone 이 정합하지 않거나, §A2 legacy ROADMAP normalization 이 필요하거나, 새 ROADMAP milestone/horizon 추가·수정이 필요하다고 판단되면 pass-through 하지 않는다. 이 경우 §B1 `planning_gate.spec_delta` 로 제안만 하고, 사용자 승인 전 §D/§E 진입·구현코드 변경·커밋 **금지**. 새 objective/horizon/milestone 을 *작성*하는 단계라면 **§B0.5 Planning cascade authoring** 으로 들어가 토론 루프로 cascade 문서를 짠다.

단, 사용자가 같은 turn 에 명시적으로 continuation 을 요청했고 §B3 continuation gate 가 이미 있는 pending/Next Candidate 를 그대로 active 로 승격할 수 있다고 판단하면, 이것은 "새 horizon 작성" 이 아니라 "승인된 후보 실행" 으로 본다. 이 경우 승격 커밋 또는 ROADMAP marker 변경 후 §A1 로 돌아가 다음 target 을 확정하고 pass-through 할 수 있다.

**정지는 옵트인.** 사용자가 이번 `/harness` 호출에서 "계획부터 보여줘"·"실행 전에 멈춰"·"플랜 먼저 확인" 처럼 **명시적으로 요청**했을 때만 §D 끝 → §E 전에 멈추고, 다음 3개를 제시한 뒤 승인을 받는다:

1. **produce 산출물 경로** (갈래별, multi-step 이면 `docs/plans/<date>-<slug>.md` plan doc 포함):
   - product: `phases/<task>/index.json` + 생성한 `step{N}.md` 목록
   - learning: 채울 `ANALYSIS.md`/`EXPERIMENT.md` 스켈레톤 + 분석/실험 대상
   - tooling: `changesets/<YYYYMMDD>-<slug>/README.md` + 영향 파일/검증 checklist
   - workflow-A: `playbooks/<slug>.md` 스켈레톤 (4섹션 빈칸)
   - workflow-B: `run.json` checklist (각 항목 `requires_authority` 표시 포함)
2. **run 이 바꿀 것 한 줄** — 어떤 파일이 생기고 어떤 커밋이 찍히나.
3. 승인 질문 — Claude 에서는 AskUserQuestion, Codex 에서는 평문 한 줄로 **"이대로 run 진행 / 계획 수정 / 중단"** 을 묻는다.

옵트인으로 멈춘 경우엔 승인 전 §E 진입·구현코드 변경·커밋 **금지**.

---

## §B3. ROADMAP lifecycle (공통 — 상위 status machine)

`ROADMAP.md` 는 갈래별 status machine(`phases/index.json`, `references/README.md`, `run.json`)을 대체하지 않는다. 대신 **현재 horizon 의 milestone 상태만 관리하는 상위 장부**다. `BACKLOG.md` 는 완료·보류·아카이브된 milestone 의 압축 이력 저장소다.

역할 분담 (상태 vs 계획 분리 — ADR 0007 cascade):
- `CLAUDE.md` = north star / 프로젝트 규칙
- `docs/OBJECTIVE.md` = 북극성 확장 (cascade 최상위, 단수, 거의 안 변함) *— 계획*
- `docs/horizons/<slug>.md` = horizon plan (담을 milestone·왜 지금·닫는 기준, horizon 당 1개) *— 계획*
- `ROADMAP.md` = current horizon / active milestones / 150줄 이하 — **상태판**(어디까지 됐나). horizon 줄은 `docs/horizons/<slug>.md` 포인터
- `docs/plans/<date>-<slug>.md` = milestone plan (step 트리, horizon 백링크) *— 계획*
- `BACKLOG.md` = completed or archived milestone ledger
- `CLAUDE.local.md` = 다음 세션 handoff (`session-end` 소유)

**`ROADMAP.md` 표준 marker 형식** (`harness:goal` horizon 줄 + `harness:milestone` block: DoD·Evidence·Gap·Status:[ ] 필수) **→ `references/planning-gates.md` §B3 참조.** marker 를 작성할 때(§B0.5 Beat 2/3) 그 형식을 쓴다.

규칙:
- `DoD` 와 `Evidence` 없는 milestone 은 자동 완료 처리 금지. checkbox 만으로 완료 판단하지 않는다.
- `blocked`/`error` 는 `ROADMAP.md` 완료 처리 금지. 필요하면 해당 milestone block 에 `- Blocked by: ...` 를 남기고 멈춘다.
- 작업 중 step/checklist 진행률은 갈래별 status machine 에 기록하고, `ROADMAP.md` 는 milestone boundary 에서만 갱신한다.
- **cascade plan docs (ADR 0007):** Objective→Horizon→Milestone→Step 을 위→아래 링크된 전용 문서로 둔다(`docs/OBJECTIVE.md`→`docs/horizons/<slug>.md`→`docs/plans/<date>-<slug>.md`→갈래 status machine). `ROADMAP.md`=*상태판*, cascade docs=*계획*. 새 horizon 을 active 로 세울 때 `templates/HORIZON_TEMPLATE.md`(+ 처음이면 `templates/OBJECTIVE_TEMPLATE.md`)로 horizon doc 을 만들고 ROADMAP `harness:goal` 줄이 그 doc 을 가리키게 한다. 진행 상태는 ROADMAP/status machine 이 정본 — cascade 체크박스는 milestone/horizon boundary 에서만 동기화(이중기록 drift 방지). cascade 가 없는 레포는 ROADMAP 만으로도 동작(optional, 점진 도입).
- `ROADMAP.md` 는 150줄 이하를 유지한다. 초과 시 완료된 milestone 부터 `BACKLOG.md` 로 3~5줄 압축 아카이브한다. active/pending milestone 은 자동 삭제 금지.
- candidate가 단일 컴포넌트/좁은 smoke라면 ROADMAP milestone으로 승격하지 말고 phase step으로 남긴다.
- active 후보는 최소 2-5 steps와 하나 이상의 통합 smoke가 자연스러워야 한다.

공통 helper: `roadmap_sync.py status | complete --milestone <ID> --evidence <path> --summary "<한 줄>" | compact --max-lines 150 --backlog BACKLOG.md | horizon-check --gap-out docs/roadmap-gap-<YYYY-MM-DD>.md`. **풀 호출 형식(HARNESS_SCRIPTS 경로 해석 포함) → `references/planning-gates.md` §B3 참조.**

**Continuation opt-in** (spine) — 기본은 milestone boundary 에서 정지. 사용자가 "이어가"·"계속"·"run next"·"가능한 만큼 계속" 을 명시 + 이미 있는 pending/Next Candidate(`DoD`·`Evidence`·`Gap`·`Status:[ ]` 완비, blocked/error 아님) 일 때만 1개를 active 로 승격하고 §A1 부터 다시 시작한다. "가능한 만큼 계속" 이 아니면 1개 실행 후 다시 boundary 정지. 새 horizon/milestone *작성*이 필요하면 멈추고 §B0.5 로 간다. **승격 가능 조건·다중 후보 선택 규칙·정지 조건 상세 → `references/planning-gates.md` §B3-continuation.**

**Milestone 완료 hook** (spine) — 완료 경계에서: ① 갈래별 gate PASS 확인 → ② milestone `DoD` 를 evidence path 로 충족 확인 → ③ `roadmap_sync.py complete` → ④ `compact --max-lines 150` → ⑤ `horizon-check`. active milestone 0개면 새 구현으로 넘어가지 말고 멈춘다(새 방향 승인 시 §B0.5). 이번 turn 에 continuation 명시 + Continuation opt-in 통과면 예외적으로 1개 승격 후 §A1 재시작. **각 단계 판정 기준·정지 조건 상세 → `references/planning-gates.md` §B3-완료hook.**

---

## 갈래별 본문 분기 — §0 에서 정한 갈래의 본문 파일을 읽고 따른다 (lazy-split)

§C(step 설계)·§D(파일 생성)·§E(실행)은 갈래마다 다르다. **이 SKILL.md 에 인라인하지 않는다** — §0 에서 정한 갈래의 아래 파일을 **반드시 읽고(Read)** 그 절차를 그대로 따른다. (호출당 1갈래만 읽어 주입 절감 — 메커니즘 canary 검증됨, 2026-06-24.)

| 갈래 | 본문 파일 |
|------|----------|
| product | `references/product.md` |
| learning | `references/learning.md` |
| tooling | `references/tooling.md` |
| workflow-A | `references/workflow-a.md` |
| workflow-B | `references/workflow-b.md` |

> 경로는 이 스킬 폴더 기준(배포본: `~/.claude/skills/harness/references/` · `~/.codex/skills/harness/references/`). **갈래 본문을 안 읽고 §C/§E 로 진입 금지.**

---

## 에러 복구 (공통)

- **error**: 사용자가 해당 status 를 `pending` 으로 되돌리고 error/blocked 메시지 삭제 후 `/harness` 재실행
- **blocked**: 사유 해결 후 동일

---

## 갈래별 status grain 한 줄 비교

| | status 위치 | step 분해 | 반복? | commit 단위 |
|---|---|---|---|---|
| product | `phases/<task>/index.json` | ✅ N steps | ❌ | step별 2-phase |
| learning | `references/README.md` 인덱스 | ❌ 1 ref = 1 step | ❌ | 1 ref/exp = 1 commit |
| tooling | `changesets/README.md` + changeset checklist | ❌ 1 changeset = 1 step | ✅ 유지보수 반복 | 1 changeset = 1 commit |
| workflow-A | `playbooks/README.md` 인덱스 | ❌ 1 pb = 1 step | ❌ | 1 playbook = 1 commit |
| workflow-B | `outputs/<기수>/<task>-<date>/run.json` | ✅ playbook 절차 | ✅ 반복 | 1 실행 = 1 commit |
