#!/usr/bin/env python3
from validate_plan_gate import validate

GOOD = """# Plan
Status: approved 2026-07-11
## Scope Boundary
- Execution mode: `continuous`
- Stop only: completed, blocked, decision_required, risk_gate, secret_required, user_stopped.
- Rollback/cleanup: revert each narrow commit and remove temp fixtures.
## Step Tree
- [ ] Step 1
  - Artifact: validator
  - Files: scripts/validator.py
  - Dependencies: none
  - Verify: test one
  - Failure probe: missing input fails
  - Commit: one changeset
- [ ] Step 2
  - Artifact: runtime guard
  - Files: scripts/guard.py
  - Dependencies: Step 1
  - Verify: test two
  - Failure probe: early stop fails
  - Commit: one changeset
## 스캐폴딩 결정
- 작업 유형: tooling
- source-of-truth: scripts/validator.py
- deploy: setup.sh both runtimes
- 테스트 표면: pytest gate suite
## 결정 로그
- status: resolved
- decision: local only
"""

assert validate(GOOD) == []
assert any("Status" in item for item in validate(GOOD.replace("approved 2026-07-11", "awaiting run approval")))
assert any("decision log" in item for item in validate(GOOD.replace("- status: resolved", "- owner: user")))
assert any("unresolved" in item for item in validate(GOOD.replace("- decision: local only", "- unresolved: choose DB")))
assert any("Verify" in item for item in validate(GOOD.replace("  - Verify: test two\n", "")))

for label, line in {
    "Artifact": "  - Artifact: runtime guard\n",
    "Files": "  - Files: scripts/guard.py\n",
    "Dependencies": "  - Dependencies: Step 1\n",
    "Failure probe": "  - Failure probe: early stop fails\n",
    "Commit": "  - Commit: one changeset\n",
}.items():
    assert any(label in item for item in validate(GOOD.replace(line, ""))), label
assert any("execution mode" in item for item in validate(GOOD.replace("- Execution mode: `continuous`\n", "")))
assert any("hard-stop" in item for item in validate(GOOD.replace("- Stop only: completed, blocked, decision_required, risk_gate, secret_required, user_stopped.\n", "")))
assert any("rollback/cleanup" in item for item in validate(GOOD.replace("- Rollback/cleanup: revert each narrow commit and remove temp fixtures.\n", "")))

# C08 lint — placeholder·빈 verify·빈 Supersedes 는 계획 packet 미완결
assert any("placeholder" in item for item in validate(GOOD.replace("local only", "TBD")))
assert any("Verify" in item for item in validate(GOOD.replace("- Verify: test two", "- Verify:")))
assert any("Supersedes" in item for item in validate(GOOD.replace("# Plan\n", "# Plan\nSupersedes:\n")))
assert validate(GOOD.replace("# Plan\n", "# Plan\nSupersedes: docs/plans/2026-07-01-old.md\n")) == []

# TM 경계 fixture (W9 TM 단독 처분, 2026-07-20 갱신) — task-master 식
# auto-decomposition packet(complexity score, leaf별 검증 계약 없음)은 여전히
# /harness plan 계약이 아니다. 2026-07-20에 dependency-graph edge 검증(missing/
# self/cycle/duplicate — validate_graph 아래 참조)을 흡수했지만, 이는 *이미 6필드
# 계약을 만족한* id-형식 leaf 위에만 얹히는 추가 체크다 — complexity score 나
# graph-without-verify-contract 를 대체 계약으로 인정하는 게 아니다. 이 fixture(
# 필드 없는 plain 'Task N (complexity: 7, depends: [])')는 여전히 FAIL 이어야 한다.
TASK_MASTER_STYLE = """# Auto-decomposed tasks
Status: generated
- [ ] Task 1 (complexity: 7, depends: [])
- [ ] Task 2 (complexity: 4, depends: [1])
- [ ] Task 3 (complexity: 9, depends: [1, 2])
"""
tm_errors = validate(TASK_MASTER_STYLE)
assert any("Status" in item for item in tm_errors)
assert any("Verify" in item for item in tm_errors)
assert any("scope boundary" in item for item in tm_errors)
assert any("결정 로그" in item or "Decision Log" in item for item in tm_errors)
assert any("스캐폴딩" in item for item in tm_errors)  # CS6: 스캐폴딩 결정 섹션 자체가 필수 (유형 enum 은 폐지)

# CS1 (2026-07-17) — 스캐폴딩 결정 완전성
# CS6: 유형 줄 없음/미등재 유형 = 신형(자기선언) 모드 — 제외 자기점검 미기재로 FAIL
assert any("검토 후 제외" in item for item in validate(GOOD.replace("- 작업 유형: tooling\n", "")))  # CS6: 유형 없음 = 신형 모드
assert any("검토 후 제외" in item for item in validate(GOOD.replace("작업 유형: tooling", "작업 유형: vibe")))  # CS6: 미등재 유형 = 신형 모드
# 축소 셋 도메인 누락 = FAIL (도메인명 특정)
assert any("테스트 표면" in item for item in validate(GOOD.replace("- 테스트 표면: pytest gate suite\n", "")))

SERVICE_SCAFFOLD = """## 스캐폴딩 결정
- 작업 유형: product-service
- frontend: Next.js 15 app router, 화면 3개(목록/상세/설정)
- backend: FastAPI, REST /api/v1 계약 명세 첨부
- data: Postgres(neon), 스키마 v1 + alembic 마이그레이션
- design: Askewly Design 토큰, entry-protocol recipes
- deploy: Vercel(FE)+Render(BE), env 목록 5종
- 관측: Sentry + 구조화 로그
"""
SERVICE_GOOD = GOOD.replace(
    "## 스캐폴딩 결정\n- 작업 유형: tooling\n- source-of-truth: scripts/validator.py\n- deploy: setup.sh both runtimes\n- 테스트 표면: pytest gate suite\n",
    SERVICE_SCAFFOLD,
)
assert validate(SERVICE_GOOD) == []
# product-service 도메인 1개 비움 = FAIL + 누락 도메인명
assert any("frontend" in item for item in validate(SERVICE_GOOD.replace("- frontend: Next.js 15 app router, 화면 3개(목록/상세/설정)", "- frontend:")))
# 해당 없음 + 이유 = PASS
assert validate(SERVICE_GOOD.replace("- 관측: Sentry + 구조화 로그", "- 관측: 해당 없음 — MVP 는 콘솔 로그만, 트래픽 후 재결정")) == []
# 해당 없음 이유 없음 = FAIL
assert any("해당 없음" in item for item in validate(SERVICE_GOOD.replace("- 관측: Sentry + 구조화 로그", "- 관측: 해당 없음")))

# 용어 lint (2026-07-17) — 발명 레벨 라벨(DP1·DD-3) = FAIL, 정상 ID(UD1·step-N)는 통과
assert any("invented hierarchy label" in item for item in validate(GOOD.replace("Step 1", "DP1 스텝")))
assert any("invented hierarchy label" in item for item in validate(GOOD.replace("Step 2", "DD-2 완료 정의")))
assert validate(GOOD.replace("Step 1", "UD1 step")) == []

print("test_validate_plan_gate: PASS")

# CS6 신형 모드 — 코어 3(별칭)+자기선언+제외 자기점검
_new = GOOD.replace("- 작업 유형: tooling\n", "").replace("## 결정 로그", "- 검토 후 제외: 화면/디자인 — CLI 도구\n\n## 결정 로그")
assert validate(_new) == [], validate(_new)
_bad = _new.replace("- 검토 후 제외: 화면/디자인 — CLI 도구", "- 검토 후 제외: 없음\n- 데이터:")
_errs = validate(_bad)
assert any("데이터" in e for e in _errs), _errs
print("plan gate tests: OK (CS6)")

# IMP-041 (2026-07-18) — 중괄호 템플릿 잔재: 펜스 밖 = FAIL, 코드 펜스 안 = PASS
assert any("template brace" in item for item in validate(GOOD.replace("Step 1", "{모듈 이름} Step 1")))
_fenced = GOOD + "\n```json\n{\"config\": {\"key\": \"value\"}}\n```\n"
assert validate(_fenced) == [], validate(_fenced)
print("test_validate_plan_gate IMP-041: PASS")

# dependency-graph edge validation (2026-07-20, plan-forge 흡수) — id 형식 leaf 헤딩
# ('- [ ] **id — slug**') 에서만 동작. plain 'Step N' 스타일(GOOD/TASK_MASTER_STYLE)은
# 건드리지 않는다 — 이미 위에서 validate(GOOD) == [] 로 확인됨(회귀 없음).
# id 는 `step-N` 이어야 한다 — OI2(2026-07-23)가 의존 값 문법을 고정한 뒤로 구 픽스처
# (`leaf-1`)는 문법 밖이라 이 파일 전체가 조용히 깨져 있었다. 아무도 이 스위트를 돌리지
# 않아서 드러나지 않았다(레포 pytest 는 the-source-repo 만 수집한다).
GRAPH_GOOD = GOOD.replace("- [ ] Step 1", "- [ ] **step-1 — validator**").replace(
    "- [ ] Step 2", "- [ ] **step-2 — guard**"
).replace("Dependencies: Step 1", "Dependencies: step-1")
assert validate(GRAPH_GOOD) == [], validate(GRAPH_GOOD)

GRAPH_CYCLE = GRAPH_GOOD.replace("Dependencies: none", "Dependencies: step-2")
cycle_errors = validate(GRAPH_CYCLE)
assert any("cycle" in e for e in cycle_errors), cycle_errors
assert any("no independent root" in e for e in cycle_errors), cycle_errors

GRAPH_MISSING = GRAPH_GOOD.replace("Dependencies: step-1", "Dependencies: step-99")
assert any("missing leaf" in e for e in validate(GRAPH_MISSING))

GRAPH_SELF = GRAPH_GOOD.replace("Dependencies: step-1", "Dependencies: step-2")
assert any("depends on itself" in e for e in validate(GRAPH_SELF))

GRAPH_DUP = GRAPH_GOOD.replace("Dependencies: step-1", "Dependencies: step-1, step-1")
assert any("duplicate dependency" in e for e in validate(GRAPH_DUP))

print("test_validate_plan_gate graph: PASS")

# CF3 step-4 (2026-07-21): 게이트가 평범한 마크다운 표기를 거부하면 안 된다.
# 정본 PLAN_TEMPLATE 조차 자기 게이트를 통과 못 했고(CF1 finding F1), 세션마다
# 형식을 역추적하느라 시간을 썼다. 선언의 *존재*는 그대로 요구하고 표기만 수용한다.
assert validate(GOOD.replace("- Execution mode: `continuous`", "- **execution mode**: `continuous`")) == []
assert validate(GOOD.replace("- Rollback/cleanup: revert", "- **rollback/cleanup**: revert")) == []
assert validate(GOOD.replace("## 결정 로그", "## 결정 로그 (run 전 사전 소진 — §B2-scope)")) == []
assert validate(GOOD.replace("## Scope Boundary", "## 범위·중단점 (run 전 scope 결정 — 확정)")) == []

# 완화가 "선언 자체를 안 봐도 된다" 로 번지면 안 된다 — 없으면 여전히 FAIL.
assert any("execution mode" in i for i in validate(GOOD.replace("- Execution mode: `continuous`", "")))
assert any("rollback" in i.lower() for i in validate(GOOD.replace("- Rollback/cleanup: revert each narrow commit and remove temp fixtures.", "")))
assert any("결정 로그" in i for i in validate(GOOD.replace("## 결정 로그", "## 잡담")))
assert any("continuous" in i for i in validate(GOOD.replace("`continuous`", "`manual`")))

print("plan gate 완화 회귀 8건 PASS")

# ── 위험 등급 (2026-07-23 DC1 step-2) ────────────────────────────────────────
# 발효일 이후 생성된 plan 의 id 형식 leaf 에만 요구한다. 두 축을 각각 박는다:
# ① 신형은 선언을 강제하고 ② 구형(발효일 이전)은 소급하지 않는다.
RISK_BASE = GRAPH_GOOD.replace(
    "# Plan", "# Plan\n> 생성: 2026-07-23 · 산출물: changeset"
)
RISK_GOOD = RISK_BASE.replace(
    "  - Artifact: validator", "  - Artifact: validator\n  - Risk: 없음 (조사)"
).replace(
    "  - Artifact: runtime guard", "  - Artifact: runtime guard\n  - Risk: 위험 (통과하던 것이 막힌다)"
)
assert validate(RISK_GOOD) == [], validate(RISK_GOOD)

# 선언 누락은 **어느 leaf 인지 지목**해야 한다 — 뭉뚱그린 실패는 진단 가치가 없다.
_missing = validate(RISK_GOOD.replace("  - Risk: 위험 (통과하던 것이 막힌다)\n", ""))
assert any("step-2" in e and "Risk" in e for e in _missing), _missing
assert not any("step-1" in e for e in _missing), _missing

# 어휘 밖 값은 거절한다(RISKY 같은 원어·자유 서술 포함 — 용어 규칙 2026-07-19).
_bad = validate(RISK_GOOD.replace("- Risk: 없음 (조사)", "- Risk: RISKY"))
assert any("어휘 밖" in e for e in _bad), _bad

# 미분류는 통과시키되 집계로 드러낸다 — 막으면 아무 값이나 적고, 안 세면 도피처가 된다.
from validate_plan_gate import validate_risk  # noqa: E402

_unclassified = RISK_GOOD.replace("- Risk: 없음 (조사)", "- Risk: 미분류 (판단 보류)")
assert validate(_unclassified) == [], validate(_unclassified)
assert validate_risk(_unclassified)[1].get("미분류") == 1, validate_risk(_unclassified)

# 소급 금지: 발효일 이전 생성 plan 은 Risk 가 없어도 통과한다.
# 근거 — 계획의 반대 프로브가 실제로 이 결함을 잡았다: 승인 완료된
# `plans/2026-07-21-mm3-eol-encoding.md` 도 id 형식이라 leaf 3개가 통째로 FAIL 났다.
_legacy = RISK_BASE.replace("> 생성: 2026-07-23", "> 생성: 2026-07-22")
assert validate(_legacy) == [], validate(_legacy)
# 생성일 줄 자체가 없는 구 plan 도 마찬가지(GRAPH_GOOD 이 그 형태다).
assert validate(GRAPH_GOOD) == [], validate(GRAPH_GOOD)

print("plan gate risk 6건 PASS")

# ── 승인 판정은 산문 언급에 속지 않는다 (2026-07-23 DC1 R1) ──────────────────
# 실측: 미승인 계획 5건이 "승인 대기 — … (승인 시 approved 로 갱신)" 이라는 *문장* 때문에
# 전부 PASS 했다. 승인 도장은 Status 값의 머리에 찍힌다.
_prose = validate(GOOD.replace("Status: approved 2026-07-11", "Status: 승인 대기 (승인 시 approved 로 갱신)"))
assert any("Status" in e for e in _prose), _prose
_prose2 = validate(GOOD.replace("Status: approved 2026-07-11", "Status: 검토 중 — approved 아님"))
assert any("Status" in e for e in _prose2), _prose2
# 정상 도장은 그대로 통과한다(실사용 형태 2종: 괄호 주석·굵게).
assert validate(GOOD.replace("Status: approved 2026-07-11", "Status: approved (2026-07-23 사용자 승인 — 전체 연쇄)")) == []
assert validate(GOOD.replace("Status: approved 2026-07-11", "Status: **completed** 2026-07-23")) == []

print("plan gate 승인 판정 4건 PASS")

# ── Status 실패 지목 분리 (2026-08-01 tax-agent 마찰 #2) ─────────────────────
# 불릿으로 쓴 `- Status: approved` 는 ^Status: 에 안 걸린다 — 이때 "approved 아님" 이
# 아니라 "Status: 줄을 못 찾았다(줄 맨 앞)" 로 지목해야 한다.
_bullet = validate(GOOD.replace("Status: approved 2026-07-11", "- Status: approved 2026-07-11"))
assert any("줄 맨 앞" in e for e in _bullet), _bullet
assert not any("approved or completed" in e for e in _bullet), _bullet
# 줄은 찾았는데 값이 미달이면 현재 값을 되비춘다.
_wrongval = validate(GOOD.replace("Status: approved 2026-07-11", "Status: draft"))
assert any("approved or completed" in e and "draft" in e for e in _wrongval), _wrongval

print("plan gate Status 지목 2건 PASS")

# ── 배차 설계 절 (2026-08-14 M18 step-1) ─────────────────────────────────────
# opt-in: 절이 없으면 무검사(기존 계획 무영향)는 위 GOOD == [] 들이 이미 증명한다.
DISPATCH_GOOD = """# Plan
> 생성: 2026-08-14
Status: approved 2026-08-14
## Scope Boundary
- Execution mode: `continuous`
- Stop only: completed, blocked, decision_required, risk_gate, secret_required, user_stopped.
- Rollback/cleanup: revert each narrow commit.
## Step Tree
- [ ] **step-1 — base**
  - Artifact: base module
  - Risk: 기계적 (순수 추가)
  - Files: scripts/base.py
  - Dependencies: none
  - Verify: pytest base
  - Failure probe: missing input fails
  - Commit: one changeset
- [ ] **step-2 — worker-a**
  - Artifact: worker a output
  - Risk: 기계적 (순수 추가)
  - Files: scripts/a.py
  - Dependencies: step-1
  - Verify: pytest a
  - Failure probe: bad input fails
  - Commit: one changeset
- [ ] **step-3 — worker-b**
  - Artifact: worker b output
  - Risk: 기계적 (순수 추가)
  - Files: scripts/b.py
  - Dependencies: step-1
  - Verify: pytest b
  - Failure probe: bad input fails
  - Commit: one changeset
## 배차 설계
- 근거: 벽시계 단축 (독립 leaf 2, 파일 겹침 없음)
- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a
- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b
## 스캐폴딩 결정
- source-of-truth: scripts/
- 검증: pytest
- 배포/운영: 해당 없음 — 로컬 fixture
- 검토 후 제외: 없음
## 결정 로그
- status: resolved
- decision: local only
"""

assert validate(DISPATCH_GOOD) == [], validate(DISPATCH_GOOD)
# probe 1 — worker 에 model 누락
_no_model = validate(DISPATCH_GOOD.replace("worker(sonnet) · 격리 worktree · 검증 pytest a", "worker() · 격리 worktree · 검증 pytest a"))
assert any("model 이 없다" in e for e in _no_model), _no_model
# probe 2 — 유령 leaf 참조
_ghost = validate(DISPATCH_GOOD.replace("- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b", "- step-9 · worker(sonnet) · 격리 worktree · 검증 pytest b"))
assert any("실재하지 않는 leaf" in e and "step-9" in e for e in _ghost), _ghost
# probe 3 — 순차 의존 leaf 의 병렬 worker 선언 (step-3 이 step-2 에 의존하도록 변형)
_seq = validate(DISPATCH_GOOD.replace("  - Dependencies: step-1\n  - Verify: pytest b", "  - Dependencies: step-2\n  - Verify: pytest b"))
assert any("순차 의존" in e for e in _seq), _seq
# 문법 밖 행 (격리 누락) 지목
_bad_row = validate(DISPATCH_GOOD.replace("- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a", "- step-2 · worker(sonnet) · 검증 pytest a"))
assert any("문법 밖" in e for e in _bad_row), _bad_row
# 근거 줄 누락
_no_gain = validate(DISPATCH_GOOD.replace("- 근거: 벽시계 단축 (독립 leaf 2, 파일 겹침 없음)\n", ""))
assert any("근거" in e for e in _no_gain), _no_gain
# inline 행은 model 불요 — 정상 통과
assert validate(DISPATCH_GOOD.replace("- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a", "- step-2 · inline · 격리 none · 검증 pytest a")) == []

print("plan gate 배차 설계 7건 PASS")
