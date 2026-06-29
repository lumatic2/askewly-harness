> harness 갈래 본문 (lazy-split, F2). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤 §0 에서 이 갈래로 판정됐을 때 읽는다. §A1/§B2-scope/§B3 등 상호참조는 SKILL.md 에 있다.

## ▶ LEARNING — 인덱스 표 패러다임 (phases/ 안 씀)

### §C-learning. Step 설계

**핵심: 1 reference = 1 step. 1 experiment = 1 step.** step 더 안 쪼갬 — ANALYSIS.md 5섹션 / EXPERIMENT.md 4섹션 자체가 작업 단위. 작성 도중엔 `pending`, 완성 시 `✅`.

작업 흐름:
1. 분석/실험할 *대상* 1개 정함 (`<handle>/<repo>` 또는 `<NN>-<slug>`)
2. 사전 준비 — 시간 박스 90분, 인용 출처+날짜 필수
3. 템플릿 복사 → 채워나감

### §D-learning. 파일 생성

#### D-1. reference 분석

**입력이 배포 사이트/제품 URL이면 backing repo 부터 해소**: WebFetch 로 footer·about 의 GitHub 링크를 찾고, 못 찾으면 사용자에게 repo URL 을 묻는다. `<handle>/<repo>` 가 확정돼야 아래로 진행 (URL 만으로 클론 못 함).

```bash
mkdir -p references/<handle>-<repo>
# (1) 실제 클론 (선택 — 분석에 코드 필요 시). 폴더 루트에 직접 (README 인덱스가 루트를 가리킴)
git clone --depth 1 <url> references/<handle>-<repo>
# ⚠ 클론의 .git 제거 — 안 지우면 embedded repo 가 돼서 형제 ANALYSIS.md 의
#   git add 가 *에러 없이 조용히 실패*한다. 기존 reference 들도 모두 plain dir.
rm -rf references/<handle>-<repo>/.git
# (2) 분석 노트 (클론과 같은 폴더)
cp references/ANALYSIS_TEMPLATE.md references/<handle>-<repo>/ANALYSIS.md
```

`.gitignore` 가 `references/*/**` 전부 무시 + `!references/*/ANALYSIS.md` 만 추적 — 클론 소스는 레포에 안 박히고 분석 노트만 추적된다.

5섹션을 채워라 (요약 / 디렉터리 / 구성요소 매핑 / 인상 패턴 / 내 정의 반영).

#### D-2. 실험
```bash
mkdir -p experiments/<NN>-<slug>
cp experiments/EXPERIMENT_TEMPLATE.md experiments/<NN>-<slug>/README.md
```

4섹션을 채워라 (가설 / 방법 / 결과 / 통찰). mock 먼저, real 다음. `verify/` 폴더에 raw 출력 박제.

#### D-3. 인덱스 표 갱신 (★ status machine 역할)

`references/README.md` 또는 `experiments/README.md` 의 인덱스 표에 새 행 추가:
```markdown
| # | 레포 (또는 실험) | 분석/실행일 | 한 줄 요약 | 5섹션/4섹션 완료 | 정의 반영 (ADR) |
|---|----------------|------------|-----------|----------------|----------------|
| 2 | EleutherAI/lm-eval | 2026-05-14 | task 218개 + 15 백엔드 | ⬜ | - |
```

작업 시작 시 ⬜ 로 추가, 완성 시 ✅ 로 변경. *이 표가 status machine*.

### §E-learning. 실행

> **게이트**: §B2 적용 — 기본 통과(한 줄 통지 후 진입), "계획부터 보여줘" 류 요청 시만 §E 전 정지. (정책 본문은 §B2 단일 출처)

#### ★ E-1. 섹션 채울 때마다 인덱스 표 진행 갱신
**트리거는 시간이 아니라 섹션 전이다.** ANALYSIS 한 섹션(또는 EXPERIMENT 한 섹션)을 채울 때마다 인덱스 표의 *진행 컬럼* (5섹션 중 몇 개 채웠는지, 예: `2/5`) 또는 별도 메모 컬럼을 갱신. 작성 완료 시 ✅.

#### E-2. Judge 규약 위반 거부
"5섹션 다 채우기 전 정의 갱신·통찰 보고 금지" — 위반 시 step 종료 거부, 사용자에게 알림.

#### E-3. 인용 강제
모든 외부 인용에 출처 URL + 접근일. 없는 인용은 작성 중 stop 후 사용자에게 요청.

#### E-4. 시간 박스
레포당 90분 / 실험당 사용자 합의 시간. 초과 임박 시 사용자에게 "이대로 stop or 계속?" 물어라 — *추정으로 5섹션 채우기 금지*.

#### E-5. commit 단위
1 reference (또는 1 experiment) = 1 commit:
```bash
git commit -m "learn: analyze <handle>/<repo> (5/5)"
git commit -m "experiment: <NN>-<slug> — <한줄통찰>"
```

#### E-6. 정의 반영
5섹션의 §5 (내 정의에 어떻게 반영) 가 비어있지 않으면, 해당 변경을 `docs/05-definition-history.md` (또는 갈래 적용 시 정의 파일) 에 v*.* 로 갱신하거나 ADR 발행. 인덱스 표 `정의 반영` 컬럼에 링크.

#### E-7. ROADMAP milestone sync
reference 5/5 또는 experiment 4/4 가 `ROADMAP.md` 의 milestone DoD 를 만족하면 §B3 helper 를 실행한다. 분석 노트가 완료됐다는 사실만으로 자동 완료하지 말고, milestone block 의 `Evidence` 와 `DoD` 가 실제 산출물과 맞는지 확인한다. 완료 시 `complete` → `compact` → `horizon-check`.

---
