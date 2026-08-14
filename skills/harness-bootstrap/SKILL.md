---
name: harness-bootstrap
description: 새 git 레포에 AI-readiness 하네스를 부팅하는 설치 스킬. "하네스 깔아줘", "프로젝트 부트스트랩", "AI-readiness 세팅", "신규 레포 초기화", "/harness-bootstrap"에 사용한다. CLAUDE.md·AGENTS.md·ROADMAP.md·docs/BACKLOG.md·docs/adr·changesets와 harness evidence ledger를 등록하며, 실행 규칙의 정본은 /harness-plan·/harness-run·/harness-done 3종과 custom-skills 문서다.
---

# /harness-bootstrap — 신규 프로젝트 하네스 부팅 (설치기)

레포에 harness 인프라를 깐다. 이 스킬은 `init-ai-readiness.sh` 의 **interactive wrapper — 설치만 담당**한다. 작업 규칙(planning gate·role lane·산출물 계약·문서 수명·배포 검증 게이트)의 정본은 `/harness-plan`·`/harness-run`·`/harness-done` SKILL.md 3종과 custom-skills 문서이며, **여기에 복제하지 않는다** (2026-07-06 HU2 — 정책 복제가 drift 원인이었음).

핵심 로직: the-source-repo `scripts/init-ai-readiness.sh` (Codex·CI 등 어디서든 호출 가능). 경로는 §3 의 해석 사슬로 찾는다 — `$HARNESS_ENGINEERING_ROOT` → `~/projects/…` → 형제 디렉터리. **이 스킬은 그 스크립트 없이는 부팅할 수 없다**(설계 — 정책·템플릿 복제가 drift 원인이었음). 없으면 명시적으로 실패한다.

## 1) 상황 파악 (조용히, 사용자에게 묻기 전)

```bash
git rev-parse --git-dir > /dev/null 2>&1 || echo "NOT_GIT"
[ -f ./CLAUDE.md ]      && echo "HAS_CLAUDE_MD"
[ -f ./ROADMAP.md ]     && echo "HAS_ROADMAP"
[ -f ./.harness/manifest.json ] && echo "HAS_HARNESS_MANIFEST"
[ -f ./package.json ]   && jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys | join(",")' package.json 2>/dev/null
[ -d ./src ] && ls ./src 2>&1 | head -5
```

- `NOT_GIT` → `git init` 자동 실행 후 진행 (한 줄 알림). 묻지 않음.
- 이미 부팅됨(HAS_HARNESS_MANIFEST) → **묻지 않고** 멱등 재실행. 기존 파일 보존(`[skip]`), `packs_added` 누적.
- 스택 감지 결과는 **보고에만** 쓴다(§4). 이걸로 무엇을 깔지 정하지 않는다 — 부팅은 언제나 코어만.

## 2) 무엇이 깔리나 — 묻지 않는다

**아무것도 묻지 않고 코어만 깐다** (2026-07-23 OI1). 코어 11개:

```
CLAUDE.md · AGENTS.md · ROADMAP.md · docs/BACKLOG.md · docs/adr/README.md
changesets/{README,CHANGESET_TEMPLATE}.md · templates/PLAN_TEMPLATE.md
.harness/manifest.json   (+ pre-commit hook · evidence ledger 등록)
```

그 밖의 **모든 것은 lazy** — 폴더도 파일도 미리 깔지 않고, 첫 문서를 만드는 쪽이 만든다.
배치 규약 정본 = `/harness-plan` 배치 규약 표. 계획은 `plans/`, 리서치는 `research/`,
완료·동결 기록은 `archive/`.

산출물별 파일은 `/harness-plan` spec readiness 가 **그 문서를 실제로 요구하는 시점**에 받는다:

| 필요해질 때 | 커맨드 | 깔리는 것 |
|---|---|---|
| PRD·아키텍처를 쓸 때 | `--add product` | `docs/PRD.md` · `docs/ARCHITECTURE.md` |
| 웹 화면을 만들 때 | `--add design` | design-pack `DESIGN.md` + lint hook (⚠ 이 배포판 미포함 — 없으면 명시적으로 실패) |
| 모바일 UI 를 만들 때 | `--add ui-mobile` | `docs/UI_GUIDE.md` |
| 첫 레포 분석을 쓸 때 | `--add analysis` | `references/` + ANALYSIS_TEMPLATE(5섹션) |
| 첫 실험·메모 | `--add experiments` / `--add notes` | `experiments/` / `notes/` |
| 첫 playbook 을 쓸 때 | `--add workflow` | `docs/DOMAIN.md` · `playbooks/` · `config/sources.md` · `data/`·`outputs/`(gitignored) |

> **왜 안 묻나.** 폴더를 미리 깔지 않으므로 부팅 시점에 가를 실체가 없다. 무엇이 필요한지는
> 그 문서를 요구하는 순간에 알고, 부팅 때 추측하면 틀린 추측이 레포 정체성 문서에 박힌다.
> 구 4갈래 질문은 2026-07-06 폐지됐는데 **질문 의식만 남아 있었다** — 그 표기가 폐지된 어휘를
> 신규 레포로 계속 출하해 실측 50개 중 15개를 오염시켰다(OI1 step-1). `--mode`/`--kind` 는
> 이제 스크립트가 **exit≠0 으로 거절**한다.

**§1 의 스택 추정은 묻기 위한 재료가 아니라 보고용 한 줄**이다 — 부팅은 추정과 무관하게 코어만 깐다.

## 3) 실행 — **Git Bash** (WSL 아님)

```bash
# 스크립트 위치를 해석한다 — 홈 배치를 전제하지 않는다(MM8, 2026-07-21).
# 없으면 조용히 넘어가지 않고 즉시 실패한다: 부트스트랩은 반쯤 되면 더 나쁘다.
INIT=""
for c in "$HARNESS_ENGINEERING_ROOT/scripts/init-ai-readiness.sh"          "$HOME/projects/the-source-repo/scripts/init-ai-readiness.sh"          "$(git rev-parse --show-toplevel 2>/dev/null)/../the-source-repo/scripts/init-ai-readiness.sh"; do
  [ -f "$c" ] && INIT="$c" && break
done
[ -n "$INIT" ] || { echo "init-ai-readiness.sh 를 못 찾았다 — the-source-repo 체크아웃 경로를 HARNESS_ENGINEERING_ROOT 로 지정하라"; exit 1; }

bash "$INIT" "$PWD" --full
```

- 팩은 나중에 `bash "$INIT" "$PWD" --add <pack>` 로 하나씩(복수 지정 가능). 부팅 시점에는 주지 않는다.
- ⚠ **WSL 경로 변환(`/mnt/c/...`) 금지** — 이 환경의 bash 는 Git Bash 다. 구버전의 `/mnt/c` 지시가 실제 에러 원인이었다(2026-07-06 사용자 보고). PowerShell 에서 부르면 `bash -c "..."` 로 감싼다.
- 출력의 `[ok]`/`[skip]`/`[warn]` 라인을 모아 보고에 사용.

## 4) 보고 (한 메시지)

1. 생성/스킵 파일 목록 (`[ok]`/`[skip]` 요약). 감지한 스택이 있으면 한 줄로 알리되 **분류로 쓰지 않는다**.
2. 다음 단계 2~3줄: CLAUDE.md 스택/규칙 채우기 → **북극성 세우기(§5)** → ROADMAP milestone 채우기 → 첫 작업은 `/harness-plan` 으로 (빈 spec 은 `/harness-plan` spec readiness 가 사용자와 채운다 — 지금 다 채울 필요 없음).
3. 산출물별 파일은 **아직 없다**는 것과, `/harness-plan` 이 필요할 때 `--add <pack>` 로 받는다는 것을 한 줄로 알린다. 웹 디자인 design-pack 은 이 배포판에 포함되지 않는다 — `--add design` 은 팩이 없으면 명시적으로 실패한다.

운영 규칙 포인터 (복제 금지): planning gate·role lanes → `/harness-plan` SKILL.md · milestone 완료·ROADMAP/BACKLOG 쓰기 소유·문서 수명(living vs record) → `/harness-done` SKILL.md. custom-skills 배포 검증(acceptance·hardening parity·evidence pack) → `custom-skills/scripts/` + docs.

## 5) 북극성 세우기 (설치 직후 — 건너뛰지 않는다)

설치가 끝나면 `CLAUDE.md` 맨 위 「북극성」 절이 채워졌는지 확인하고, **비어 있으면 그 자리에서 `/harness-plan` 계획 작성(북극성 세우기)으로 넘긴다**(문구는 사용자 소유 — 승인 후에만 기록). 부팅만 하고 북극성 없이 남겨두지 않는다 — 뒤따르는 milestone·계획서가 전부 이 절을 백링크한다. (2026-07-23 재조립 C4 로 구 `OBJECTIVE.md` 는 은퇴 — 스캐폴드가 이 절을 빈 채로 깔아 준다.)

- **문구는 사용자 소유**: 에이전트는 후보 북극성 문구를 대화로 제안하고, **사용자가 명시 승인한 뒤에만** 파일에 기록한다. 승인 전 자율 작성 금지 (북극성 소유권, 2026-07-19).
- 부팅 직후라 재료가 얇으면 북극성 설계의 **재료 수집(리서치) 단계**가 기본이다 — 생략은 "조사 불요 — <이유>" 명시 시만.
- 사용자가 "지금 말고"라고 하면 보고 마지막 줄에 남은 숙제로 한 줄 남기고 끝낸다.

## 주의

- **멱등 + additive**: 재실행해도 기존 파일 보존. 팩 추가는 manifest `packs_added` 에 누적된다 — 이건 *기록*이지 레포 분류가 아니다(분류 개념은 2026-07-23 폐지).
- repo 가 크거나 구조가 바뀌면 nested `AGENTS.md`/`CLAUDE.md` landmark 후보를 보고에 남긴다 (생성 규칙 정본은 `/harness-plan`·context-manager).

## 짝 스킬

- `/harness-plan` → `/harness-run` → `/harness-done` — 부팅 후 실제 작업 흐름(계획→구현·렌더 검증→마감)
- `/skill-creator` — 부팅 후 프로젝트 전용 스킬

## 출처

- jha0313/harness_framework 템플릿 흡수 (2026-05-14) · 4분기 질문 → 산출물 팩 (2026-07-06 HU2) → **팩 선택 질문까지 제거·전면 lazy** (2026-07-23 OI1, one-invocation-harness horizon)
