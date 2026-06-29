> harness 갈래 본문 (lazy-split, F2). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤 §0 에서 이 갈래로 판정됐을 때 읽는다. §A1/§B2-scope/§B3 등 상호참조는 SKILL.md 에 있다.

## ▶ TOOLING — changeset 패러다임 (스킬·스크립트·런타임 유지보수)

### §C-tooling. Step 설계

**핵심: 1 tooling changeset = 1 step.** 스킬 문서, bootstrap script, verifier, setup/sync, acceptance gate, host hardening 문서처럼 도구 자체를 바꾸는 작업은 learning reference 가 아니라 tooling changeset 으로 다룬다.

작업 흐름:
1. 이번 changeset 의 target 을 정함 (`<YYYYMMDD>-<slug>`)
2. 영향 파일과 배포 경로를 먼저 식별
3. 검증 checklist 를 changeset 에 적고 나서 패치
4. source-of-truth 와 deployed copy 가 갈라지지 않았는지 확인

### §D-tooling. 파일 생성

```bash
mkdir -p changesets/<YYYYMMDD>-<slug>
cp changesets/CHANGESET_TEMPLATE.md changesets/<YYYYMMDD>-<slug>/README.md
```

`changesets/README.md` 인덱스 표에 새 행 추가:
```markdown
| # | Changeset | 날짜 | Scope | Verification | Status |
|---|-----------|------|-------|--------------|--------|
| 2 | {YYYYMMDD-slug} | YYYY-MM-DD | {skill/script scope} | 0/4 | in_progress |
```

`README.md` 에 반드시 채울 항목:
- Target: 연결할 ROADMAP milestone
- Scope: 영향 파일, 이유, expected effect
- Contract: source of truth, deploy/sync target, compatibility, out of scope
- Verification: targeted tests, smoke, sync/deploy, deployed grep, dirty-tree check

### §E-tooling. 실행

> **게이트**: §B2 적용 — 기본 통과(한 줄 통지 후 진입), "계획부터 보여줘" 류 요청 시만 §E 전 정지. (정책 본문은 §B2 단일 출처)

#### ★ E-1. verification 항목 전이마다 changeset 갱신
**트리거는 시간이 아니라 검증 항목 전이다.** targeted tests, smoke, sync/deploy, deployed grep 중 하나가 끝나는 시점에 `changesets/<slug>/README.md` 와 인덱스 표를 갱신한다. 완료 보고 시점에 checklist 가 비어 있으면 완료 금지.

#### E-2. source-of-truth 우선
custom skill 변경의 canonical source 는 보통 스킬 소스 레포의 `<skill>/SKILL.md` 이다. `~/.codex/skills/...` 와 `~/.claude/skills/...` 는 배포본이므로 직접 수정하지 말고 `bash setup.sh` 같은 sync 경로로 반영한다. 예외가 있으면 changeset Contract 에 명시한다.

#### E-3. 영향 파일 확인
패치 전후로 `git status --short`, 관련 `rg`, targeted diff 를 확인한다. unrelated dirty file 은 되돌리지 않는다. 영향받는 파일이 늘어나면 changeset Scope 를 갱신한다.

#### E-4. 검증
변경 성격에 맞춰 최소 하나 이상의 targeted test 를 실행한다. SKILL.md 또는 배포 계약이 바뀌면 아래를 우선한다:

```bash
cd <your-skills-repo>
bash setup.sh
python scripts/skill-trigger-acceptance.py
python scripts/hardening-parity-check.py
```

harness runtime script 가 바뀌면 해당 repo 의 focused test/smoke 를 실행한다:
```bash
python scripts/test_roadmap_sync.py
python scripts/test_verify_run.py
bash -n scripts/init-ai-readiness.sh
```

#### E-5. commit 단위
1 changeset = 1 commit. 스킬 source, runtime script, template, tests, changeset record 를 한 커밋으로 묶는다. 배포본 sync 결과가 별도 repo/file 로 남는 구조면 changeset Result 에 evidence 로 적는다.

#### E-6. ROADMAP milestone sync
changeset verification 이 `ROADMAP.md` milestone DoD 를 만족하면 §B3 helper 를 실행한다. sync/deploy evidence 가 필요한 milestone 에서 source patch 만으로 완료 처리하지 않는다. 완료 시 `complete` → `compact` → `horizon-check`.

---
