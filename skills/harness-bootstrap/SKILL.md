---
name: harness-bootstrap
description: 새 git 레포에 AI-readiness 하네스를 부팅한다 — pre-commit hook(hallucinated path 차단) + CLAUDE.md + AGENTS.md + ROADMAP.md(current horizon, 150줄 budget) + BACKLOG.md(완료 milestone archive) + docs/adr/ + 갈래별(product/learning/tooling/workflow) 필수 파일 + harness evidence ledger 자동 등록. "하네스 깔아줘", "프로젝트 부트스트랩", "claude.md 자동생성", "AI-readiness 세팅", "신규 레포 초기화", "init harness" 등의 의도 감지 시 사용. /harness-bootstrap 호출 시 사용.
---

# /harness-bootstrap — 신규 프로젝트 하네스 부팅

빈 git 레포(또는 기존 레포)에 AI 에이전트가 협업할 수 있는 최소 인프라를 깐다. **갈래 4개** 로 분기 — 갈래마다 *judge 위치*가 다르고(v2.0 정의), 그 차이가 필수 파일과 CLAUDE.md 의 judge 강제 한 줄에 박힌다. Codex 에서는 `AGENTS.md` 를 별도 stub 으로 생성해 `CLAUDE.md`/`ROADMAP.md` 를 읽도록 연결한다. `ROADMAP.md` 는 current horizon 과 active milestone 만 담고 150줄 이하로 유지하며, 완료 milestone 은 `BACKLOG.md` 로 압축 아카이브한다. ROADMAP/BACKLOG 쓰기 소유자는 `/harness` 이고, `session-end` 는 ROADMAP 을 read-only 로 확인한 뒤 `CLAUDE.local.md` handoff 에만 반영한다.

핵심 로직은 `~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh` (이 스킬과 함께 번들 — Codex·CI 등 다른 곳에서도 직접 호출 가능). 이 스킬은 그 위의 **interactive wrapper**.

## 1) 상황 파악 (조용히, 사용자에게 묻기 전)

```bash
git rev-parse --git-dir > /dev/null 2>&1 || echo "NOT_GIT"
[ -f ./CLAUDE.md ]      && echo "HAS_CLAUDE_MD"
[ -d ./docs/adr ]       && echo "HAS_ADR"
[ -f ./docs/PRD.md ]    && echo "HAS_PRD"
[ -f ./docs/DOMAIN.md ] && echo "HAS_DOMAIN"
[ -f ./ROADMAP.md ]     && echo "HAS_ROADMAP"
[ -f ./BACKLOG.md ]     && echo "HAS_BACKLOG"
[ -f ./.harness/manifest.json ] && echo "HAS_HARNESS_MANIFEST"
[ -f ./package.json ]   && jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys | join(",")' package.json
[ -d ./src ] && ls ./src 2>&1 | head -5
```

판정:
- `NOT_GIT` → `git init` 자동 실행 후 진행 (한 줄 알림: `[ok] git init (was not a repo)`). 사용자에게 따로 묻지 않음
- 모든 파일 이미 있으면 → "이미 부팅됨. 추가 갈래 capability 를 더할까?" 확인. 재실행은 기존 갈래를 바꾸지 않고 `.harness/manifest.json` 의 `modes_enabled` 에 추가 기록한다.
- 스택 추정으로 mode/kind 추정 (Q1·Q2 의 기본 선택지로):
  - next/react/vue/svelte/astro → product/web
  - expo/react-native/flutter → product/mobile
  - fastapi/express/nest/cli scripts → product/backend
  - jupyter / 실험 폴더 위주 → learning
  - SKILL.md / setup·sync·verifier scripts 위주 (스킬·툴 유지보수 레포) → tooling
  - playbook·data 디렉토리 + 도메인 키워드 → workflow

## 2) 사용자에게 묻기

Claude 에서 AskUserQuestion 이 가능하면 2단으로 묻는다. Codex 에서는 AskUserQuestion 을 가정하지 않는다. 스택/파일로 mode·kind 를 합리적으로 추정할 수 있으면 기본값으로 진행하고, 추정이 위험할 때만 평문 한 줄 질문으로 묻는다.

**Q1 — 무엇을 만드는 레포?** (single-select)
- **Product** — 출시할 무언가 (web/mobile/backend·CLI)
- **Learning/Research** — 공부·실험·정리 (예: harness-engineering 같은 학습 레포)
- **Tooling/Maintenance** — 스킬·스크립트·런타임 유지보수
- **Workflow/Ops** — 반복 업무 자동화 (세무·회계·운영)

**Q2 — (Product 선택 시에만) 세부 종류?** (single-select)
- **Web app** — UI_GUIDE(web) + PRD + ARCHITECTURE
- **Mobile app** — UI_GUIDE(mobile, RN/Flutter) + PRD + ARCHITECTURE
- **Backend / CLI / lib** — UI_GUIDE 생략, PRD + ARCHITECTURE 만

Learning/Tooling/Workflow 은 Q2 없이 바로 실행.

## 3) 실행

```bash
MODE="..."     # product | learning | tooling | workflow
KIND="..."     # product 일 때만 — web | mobile | backend
ARGS="--full --mode $MODE"
[[ "$MODE" == "product" ]] && ARGS="$ARGS --kind $KIND"
bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh "$PWD" $ARGS
```

실행 결과 `.harness/manifest.json` 이 생성/갱신된다:
- `primary_mode`: 최초 또는 주된 repo orientation. 기존 값이 있으면 보존한다.
- `modes_enabled`: bootstrap 으로 추가된 갈래 capability 목록. 재실행 시 누적된다.
- `/harness` 는 이 manifest 를 읽되, 최종 mode 는 사용자 의도와 ROADMAP target 으로 정한다.

Windows PowerShell + WSL bash 에서는 현재 디렉터리를 WSL 경로로 변환해 넘긴다 (`~` 는 bash home 으로 풀린다):

```powershell
$repo = (Resolve-Path .).Path -replace '\\','/' -replace '^C:','/mnt/c'
bash -lc "~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh '$repo' --full --mode learning"
```

출력에서 `[ok]`/`[skip]`/`[warn]` 라인을 모아 사용자 보고에 사용.

## 4) 후속 안내 (한 메시지로, 갈래별)

### Thin non-trivial planning gate

`/harness` 실행 중 non-trivial 작업은 바로 TODO로 쪼개지 않고 얇은 planning gate를 통과한다.

non-trivial 기준:
- 여러 task / 여러 file / 여러 session
- product behavior, API, data model, 권한, 결제, 외부 연동, 배포면 변경
- security, secret, supply chain, protected file 영향
- 기존 spec, ROADMAP, ADR, 과거 판단과 충돌 가능성

필수 planning block:
- `team_validation_mode`: `not_required_lightweight` / `native` / `subagent` / `manual-pass` / `unavailable`
- `spec_delta` 또는 `spec_skip_reason`
- Product / Architecture / Security / QA / Skeptic 관점 검토
- source code 변경이면 test/smoke/review/evidence DoD

이 gate는 full Plans.md 시스템을 강제하지 않는다. 목적은 큰 작업의 drift를 막는 최소 계약이다.

### Product (web/mobile)
```
[OK] 하네스 부팅 완료 (product / {kind})

생성:
- .git/hooks/pre-commit (hallucinated path 차단)
- .harness/manifest.json (primary_mode + modes_enabled; 재실행 시 capability 누적)
- CLAUDE.md (skeleton + judge 한 줄: lint·테스트 통과 강제)
- AGENTS.md (Codex stub — CLAUDE.md/ROADMAP.md 읽기 유도)
- ROADMAP.md (current horizon·active milestone·DoD/Evidence marker, 150줄 budget)
- BACKLOG.md (완료·보류·아카이브 milestone 압축 이력)
- docs/adr/README.md
- docs/PRD.md / docs/ARCHITECTURE.md
- {web → 루트 DESIGN.md (Google Labs DESIGN.md alpha 형식 — 도구 자동 read) / mobile → docs/UI_GUIDE.md (44pt 터치 + safe area 표)}
다음 단계:
1. CLAUDE.md § 기술 스택 / 작업 방식 채우기
2. ROADMAP.md Current Horizon·M1~M2 DoD/Evidence 채우기
3. docs/PRD.md 목표·핵심기능 채우기
4. {web → DESIGN.md colors/typography 토큰 + Do's and Don'ts 채우기 / mobile → docs/UI_GUIDE.md 색상 토큰 + 안티패턴 3-5개 골라 박기}
5. 첫 ADR 작성: docs/adr/0001-{title}.md

※ PRD·ARCHITECTURE·핵심 결정(백엔드·인증·디자인·스코프)을 지금 직접 채워도 되고,
  비워 두면 `/harness` 첫 product 작업의 §B0 Spec gate 가 사용자와 합의해 채운다(빈 스켈레톤 위 구현 방지).

운영 규칙:
- ROADMAP/BACKLOG 쓰기 소유자는 `/harness`
- milestone 완료·compact·horizon-check 는 `/harness` 의 `roadmap_sync.py` 로 처리
- `session-end` 는 ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 `CLAUDE.local.md` handoff 에만 반영
```

**web 인 경우 — 디자인 하네스 핸드오프 (AskUserQuestion 한 번):** 부팅 보고 직후 "디자인 시스템도 지금 깔까? (`/design-bootstrap` — DESIGN.md + lint + 선택 VRT)" 를 묻는다. Yes 면 바로 `/design-bootstrap` 으로 이어가고(UI_GUIDE 보다 본격적), No 면 위 3번 UI_GUIDE 만으로 충분. mobile/backend 는 묻지 않음(design-bootstrap 은 web 전용).

### Product (backend)
UI_GUIDE 줄만 빼고 동일.

### Learning
```
[OK] 하네스 부팅 완료 (learning)

생성:
- .git/hooks/pre-commit
- .harness/manifest.json (primary_mode + modes_enabled; 재실행 시 capability 누적)
- CLAUDE.md (skeleton + judge 한 줄: 5섹션 다 채우기 전 통찰 보고 금지)
- AGENTS.md (Codex stub — CLAUDE.md/ROADMAP.md 읽기 유도)
- docs/adr/README.md
- ROADMAP.md (current horizon·active milestone·DoD/Evidence marker, 150줄 budget)
- BACKLOG.md (완료·보류·아카이브 milestone 압축 이력)
- references/README.md + ANALYSIS_TEMPLATE.md (5섹션)
- experiments/README.md + EXPERIMENT_TEMPLATE.md (4섹션)
- notes/ (자유 형식)
다음 단계:
1. ROADMAP.md Current Horizon·M1~M3 DoD/Evidence 채우기
2. 첫 reference: references/<handle>-<repo>/ 클론 후 ANALYSIS_TEMPLATE 복사
3. 5섹션 다 채워야 정의 갱신·통찰 보고 가능 (judge 강제)

운영 규칙:
- ROADMAP/BACKLOG 쓰기 소유자는 `/harness`
- milestone 완료·compact·horizon-check 는 `/harness` 의 `roadmap_sync.py` 로 처리
- `session-end` 는 ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 `CLAUDE.local.md` handoff 에만 반영
```

### Tooling
```
[OK] 하네스 부팅 완료 (tooling)

생성:
- .git/hooks/pre-commit
- .harness/manifest.json (primary_mode + modes_enabled; 재실행 시 capability 누적)
- CLAUDE.md (skeleton + judge 한 줄: test/smoke/sync evidence 없이는 완료 보고 금지)
- AGENTS.md (Codex stub — CLAUDE.md/ROADMAP.md 읽기 유도)
- docs/adr/README.md
- ROADMAP.md (current horizon·active milestone·DoD/Evidence marker, 150줄 budget)
- BACKLOG.md (완료·보류·아카이브 milestone 압축 이력)
- changesets/README.md + CHANGESET_TEMPLATE.md (1 changeset = 1 tooling step)
다음 단계:
1. ROADMAP.md Current Horizon·T1~T2 DoD/Evidence 채우기
2. changesets/<YYYYMMDD>-<slug>/README.md 생성
3. 영향 파일·source of truth·deploy/sync target·검증 커맨드 기록
4. SKILL.md 변경 시 setup.sh sync + trigger acceptance + hardening parity 확인

운영 규칙:
- ROADMAP/BACKLOG 쓰기 소유자는 `/harness`
- milestone 완료·compact·horizon-check 는 `/harness` 의 `roadmap_sync.py` 로 처리
- `session-end` 는 ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 `CLAUDE.local.md` handoff 에만 반영
```

### Workflow
```
[OK] 하네스 부팅 완료 (workflow)

생성:
- .git/hooks/pre-commit
- .harness/manifest.json (primary_mode + modes_enabled; 재실행 시 capability 누적)
- CLAUDE.md (skeleton + judge 한 줄: 외부 권위 인용 없으면 답변 금지)
- AGENTS.md (Codex stub — CLAUDE.md/ROADMAP.md 읽기 유도)
- ROADMAP.md (current horizon·active milestone·DoD/Evidence marker, 150줄 budget)
- BACKLOG.md (완료·보류·아카이브 milestone 압축 이력)
- docs/adr/README.md
- docs/DOMAIN.md (PRD 자리 — 법규·기준일·정의)
- playbooks/README.md + PLAYBOOK_TEMPLATE.md (입력/절차/체크리스트/근거★)
- data/ outputs/ (gitignored, .gitignore 자동 패치)
- config/sources.md (외부 API·도구 카탈로그)
다음 단계:
1. ROADMAP.md Current Horizon·M1~M2 DoD/Evidence 채우기
2. docs/DOMAIN.md 핵심 법규·기준일·정의 채우기
3. config/sources.md 외부 도구 카탈로그 채우기 (KOSIS/DART/law-mcp 등)
4. 첫 playbook: playbooks/<task>.md (PLAYBOOK_TEMPLATE 복사) — 근거 섹션 필수

운영 규칙:
- ROADMAP/BACKLOG 쓰기 소유자는 `/harness`
- milestone 완료·compact·horizon-check 는 `/harness` 의 `roadmap_sync.py` 로 처리
- `session-end` 는 ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 `CLAUDE.local.md` handoff 에만 반영
```

## 주의

- **멱등**: 같은 디렉토리에 다시 실행해도 기존 파일은 보존 (`[skip]` 표시)
- **git repo 가 아니면 자동 `git init`** — 사용자가 `/harness-bootstrap` 호출했다는 것 자체가 부팅 의도. 묻지 말고 init 후 진행
- **갈래 선택 후 재실행은 additive** — 다른 갈래로 다시 부팅하면 새 갈래 파일이 *추가* 되고 `.harness/manifest.json` 의 `modes_enabled` 에 누적된다(기존 파일은 안 지움). `primary_mode` 는 자동 변경하지 않는다. `/harness` 는 파일 존재만으로 전체 모드를 바꾸지 말고 이번 run 의 의도와 ROADMAP target 으로 선택한다. primary 자체를 바꾸려면 사용자 승인 후 ROADMAP/manifest/불필요 파일 정리를 별도 migration 으로 처리한다.
- 다른 AI 도구 (Codex 등) 에서 같은 부팅이 필요하면 스크립트를 직접 호출하라고 안내. Windows PowerShell 에서는 위의 WSL 절대 경로 예시를 우선 사용:
  `bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh <repo> --full --mode <product|learning|tooling|workflow> [--kind <web|mobile|backend>]`

## 짝 스킬
- `/design-bootstrap` — Product/web 인 경우 UI_GUIDE 보다 더 본격적인 디자인 시스템 (lint + VRT 포함). product/web 부팅 후 흐름 권장
- `/skill-creator` — 부팅 후 프로젝트 전용 스킬 만들 때

## 출처
- jha0313/harness_framework 의 docs/{PRD,ARCHITECTURE,UI_GUIDE,ADR}.md 템플릿 흡수
- 갈래 4분기·judge 위치 차이는 harness-engineering 정의 작업에서 도출 (자세한 배경은 패키지 README 참조)
