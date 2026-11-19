#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

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
# 2026-09-30: 의존이 있으면 derive_waves 가 다른 wave 로 가르고 워커는 wave 단위로 순차 실행된다 → 정상.
# 옛 기대(FAIL)는 worker 행 = 동시 실행이던 M18 의미. 같은 wave 안의 의존 쌍은 wave 파생 자체가 갈라 놓으므로 생기지 않는다.
assert _seq == [], _seq
# 문법 밖 행 (격리 누락) 지목
_bad_row = validate(DISPATCH_GOOD.replace("- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a", "- step-2 · worker(sonnet) · 검증 pytest a"))
assert any("문법 밖" in e for e in _bad_row), _bad_row
# 근거 줄 누락
_no_gain = validate(DISPATCH_GOOD.replace("- 근거: 벽시계 단축 (독립 leaf 2, 파일 겹침 없음)\n", ""))
assert any("근거" in e for e in _no_gain), _no_gain
# inline 행은 model 불요 — 정상 통과
assert validate(DISPATCH_GOOD.replace("- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a", "- step-2 · inline · 격리 none · 검증 pytest a")) == []

print("plan gate 배차 설계 7건 PASS")

# ── M23 step-7 (2026-08-22): 단가 이득 + 계획 모델 상한 ───────────────────────
# 구 문법 무오탐은 위 DISPATCH_GOOD(생성 2026-08-14 < 발효일) == [] 가 이미 증명.
_M23 = DISPATCH_GOOD.replace("> 생성: 2026-08-14", "> 생성: 2026-08-22").replace(
    "- 근거: 벽시계 단축 (독립 leaf 2, 파일 겹침 없음)",
    "- 근거: 단가 (명세 고정 leaf, 부모는 검증만)\n- 계획 모델: fable",
)
assert validate(_M23) == [], validate(_M23)
# 발효일 이후 + worker 행 + 계획 모델 줄 없음 → FAIL
_no_cap = validate(DISPATCH_GOOD.replace("> 생성: 2026-08-14", "> 생성: 2026-08-22"))
assert any("계획 모델" in e for e in _no_cap), _no_cap
# 상한 위반: 계획 모델 sonnet < worker(opus) → FAIL
_inv = validate(
    _M23.replace("- 계획 모델: fable", "- 계획 모델: sonnet").replace(
        "- step-2 · worker(sonnet)", "- step-2 · worker(opus)"
    )
)
assert any("상한 위반" in e for e in _inv), _inv
# 서열 미상 모델 → FAIL
_unk = validate(_M23.replace("- step-2 · worker(sonnet)", "- step-2 · worker(gpt5)"))
assert any("서열 미상" in e for e in _unk), _unk

print("plan gate 배차 모델 상한 4건 PASS")

# ── 2026-09-30: 동시 집합 ≥2 이면 배차 절 필수 + wave 커버리지 ───────────────
_P30 = _M23.replace("> 생성: 2026-08-22", "> 생성: 2026-09-30").replace(
    "- Rollback/cleanup: revert each narrow commit.\n",
    "- Rollback/cleanup: revert each narrow commit.\n- 되돌리기 어려운 동작: 없음\n",
)
assert validate(_P30) == [], validate(_P30)  # 절 있음 + wave(step-2 step-3) worker 2 → PASS
_no_section = _P30.split("## 배차 설계")[0] + "## 스캐폴딩 결정" + _P30.split("## 스캐폴딩 결정")[1]
assert any("배차 설계` 절이 없다" in e for e in validate(_no_section)), validate(_no_section)
# 발효일 전 생성이면 무검사(기존 계획 동결)
_old = _no_section.replace("> 생성: 2026-09-30", "> 생성: 2026-09-29")
assert validate(_old) == [], validate(_old)
# wave 2 leaf 중 worker 1 → 부모 inline 1 허용이라 PASS · worker 0 → FAIL
_one = _P30.replace("- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b", "- step-3 · inline · 격리 none · 검증 pytest b")
assert validate(_one) == [], validate(_one)
_zero = _one.replace("- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a", "- step-2 · inline · 격리 none · 검증 pytest a")
assert any("worker 행이 0개" in e for e in validate(_zero)), validate(_zero)
# 순차(step-3 이 step-2 의존)면 wave 가 전부 1개 → 절 없어도 PASS
_seq30 = _no_section.replace("  - Dependencies: step-1\n  - Verify: pytest b", "  - Dependencies: step-2\n  - Verify: pytest b")
assert validate(_seq30) == [], validate(_seq30)
print("plan gate 배차 필수·wave 커버리지 5건 PASS")
# 2026-11-07: 행에 effort·researcher 를 적을 수 있다
_row2 = "- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a"
_eff = _P30.replace(_row2, "- step-2 · worker(sonnet, high) · 격리 none · 검증 pytest a")
assert validate(_eff) == [], validate(_eff)
_bad_eff = _P30.replace(_row2, "- step-2 · worker(sonnet, turbo) · 격리 none · 검증 pytest a")
assert any("effort 미상 turbo" in e for e in validate(_bad_eff)), validate(_bad_eff)
_res = _P30.replace(_row2, "- step-2 · researcher · 격리 none · 검증 pytest a")
assert validate(_res) == [], validate(_res)
_res2 = _res.replace("- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b", "- step-3 · researcher · 격리 none · 검증 pytest b")
assert validate(_res2) == [], validate(_res2)
print("plan gate effort·researcher 행 4건 PASS")
# 다른 wave 의 워커끼리는 순차가 정상 (2026-09-30 M40 첫 실전) — step-4 가 step-2·3 뒤 wave 에서 worker
_w3 = _P30.replace(
    "## 배차 설계",
    "- [ ] **step-4 — after**\n  - Artifact: merged\n  - Risk: 기계적 (순수 추가)\n  - Files: scripts/d.py\n"
    "  - Dependencies: step-2, step-3\n  - Verify: pytest d\n  - Failure probe: bad input fails\n  - Commit: one changeset\n## 배차 설계",
).replace(
    "- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b",
    "- step-3 · worker(sonnet) · 격리 worktree · 검증 pytest b\n- step-4 · worker(sonnet) · 격리 none · 검증 pytest d",
)
assert validate(_w3) == [], validate(_w3)
print("plan gate 다른 wave 워커 순차 허용 1건 PASS")


# ── M6 step-2: --pre-approval 은 Status **값 판정** 하나만 면제한다 ────────────
# 승인 전 계획서는 정의상 draft 라 게이트가 항상 빨갛고, "Status 하나만 남았다"는
# 판정에 사람이 매번 꼈다(M6 D3). 면제 범위가 새면 게이트를 무력화하는 우회로가 된다.

DRAFT = GOOD.replace("Status: approved 2026-07-11", "Status: draft (승인 대기)")

# 1) 승인 전 계획서가 플래그로 통과한다
assert validate(DRAFT, pre_approval=True) == [], validate(DRAFT, pre_approval=True)
# 플래그 없이는 기존대로 Status 로 막힌다 (무회귀)
assert any("Status" in e for e in validate(DRAFT)), validate(DRAFT)

# 2) `Status:` 줄 **부재**는 플래그가 있어도 FAIL — 부재 검사와 값 검사는 별개다
_no_status = DRAFT.replace("Status: draft (승인 대기)" + chr(10), "")
assert any("no `Status:` line" in e for e in validate(_no_status, pre_approval=True)),     validate(_no_status, pre_approval=True)

# 3) 필수 항목 결손은 플래그가 있어도 FAIL
_no_verify = DRAFT.replace("  - Verify: test two" + chr(10), "")
assert any("Verify" in e for e in validate(_no_verify, pre_approval=True))
# 결정 로그 미소진도 그대로 막힌다
_unresolved = DRAFT.replace("- decision: local only", "- unresolved: choose DB")
assert any("unresolved" in e for e in validate(_unresolved, pre_approval=True))
# leaf 2개 미만도 그대로 막힌다
assert any("two top-level" in e for e in validate(
    "Status: draft" + chr(10) + "## Scope Boundary" + chr(10), pre_approval=True))

# 4) Risk 어휘 위반은 플래그가 있어도 FAIL (2026-07-24 이후 생성 계획서에만 걸리는 규칙)
_risk_bad = DISPATCH_GOOD.replace("Status: approved 2026-07-24", "Status: draft").replace(
    "  - Risk: 기계적 (순수 추가)", "  - Risk: 높음 (감으로 적었다)", 1)
_risk_errors = validate(_risk_bad, pre_approval=True)
assert any("Risk" in e for e in _risk_errors), _risk_errors

# 5) 승인 완료된 계획서는 두 모드에서 똑같이 통과한다
assert validate(GOOD) == validate(GOOD, pre_approval=True) == []

# 6) 기본값은 면제 없음 — 파라미터를 안 주면 지금까지와 같다
assert any("Status" in e for e in validate(DRAFT))

# 7) approve_harness_plan 은 이 플래그를 전달하지 않는다 (승인 등록은 승인 어휘를 요구한다).
#    나중에 누가 흘리는 것을 막는 회귀 케이스다.
_approve_src = (Path(__file__).resolve().parent / "approve_harness_plan.py").read_text(encoding="utf-8")
assert "--pre-approval" not in _approve_src and "pre_approval" not in _approve_src,     "approve_harness_plan 이 pre-approval 을 validator 에 흘리고 있다"

# 8) CLI 표면 — 플래그가 실제로 붙어 있고 exit code 가 갈린다
_gate = Path(__file__).resolve().parent / "validate_plan_gate.py"
import tempfile
with tempfile.TemporaryDirectory() as _d:
    _plan = Path(_d) / "draft.md"
    _plan.write_text(DRAFT, encoding="utf-8")
    assert subprocess.run([sys.executable, str(_gate), str(_plan)]).returncode == 1
    assert subprocess.run([sys.executable, str(_gate), str(_plan), "--pre-approval"]).returncode == 0

print("plan gate --pre-approval 8건 PASS")

# ── M7 step-2: 검사 어휘 정정 + 펜스 표면 통일 (2026-08-20 D1·D4) ─────────────
# 코퍼스 실측(before 스냅샷): bare 'PLACEHOLDER' 히트 60 중 54 가 UI 서술의 평범한
# 명사였다. 전역 스캔에서 빼고, 남은 5종은 산문에서 여전히 잡혀야 한다(단정형 probe).

# 1) UI 서술 문장이 통과한다 — 구현 전 FAIL 하던 오탐의 재구성
_ui = GOOD.replace("- decision: local only", "- decision: 빈 상태에는 placeholder 안내 문구를 보여준다")
assert validate(_ui) == [], validate(_ui)

# 2) 단정형 probe — 펜스 밖 산문에 남은 어휘 5종이 있으면 **반드시** FAIL.
#    통과하면 어휘를 너무 깎은 것이다.
for _tok in ("TBD", "TODO", "FIXME", "미정", "추후 결정"):
    _hit = validate(GOOD.replace("- decision: local only", f"- decision: {_tok}"))
    assert any("placeholder marker" in e for e in _hit), (_tok, _hit)

# 3) 코드 펜스 안의 어휘는 통과한다 (어휘 스캔도 펜스 제거 사본을 본다 — 표면 통일)
_fenced_tok = GOOD + "\n```text\nTODO: 이 줄은 예시다\nTBD\n```\n"
assert validate(_fenced_tok) == [], validate(_fenced_tok)

# 4) 줄 번호 회귀 — 펜스가 앞에 있어도 보고된 줄 번호가 원문 줄 번호와 일치한다
#    (개행 유지 치환이라 사본과 원문의 줄 수는 같다 — 오프셋 혼용 회귀 방지)
_numbered = GOOD + "\n```json\n{\"k\": 1}\n```\n- note: TBD\n"
_expected_line = _numbered[:_numbered.index("- note: TBD")].count("\n") + 1
_line_errs = validate(_numbered)
assert any(f"line {_expected_line}:" in e and "placeholder marker" in e for e in _line_errs), (_expected_line, _line_errs)

# 5) 필드 값용 정규식은 6종 전부를 유지한다 (D4 불변식 — step-4 가 소비)
from validate_plan_gate import FIELD_PLACEHOLDER, PLACEHOLDER as _GLOBAL_PLACEHOLDER  # noqa: E402
assert FIELD_PLACEHOLDER.search("PLACEHOLDER"), "필드용 정규식이 PLACEHOLDER 를 놓친다"
assert not _GLOBAL_PLACEHOLDER.search("placeholder 안내"), "전역 정규식에 PLACEHOLDER 가 남아 있다"

print("plan gate M7 어휘·펜스 표면 9건 PASS")

# ── M7 step-3: 면제 표면 2종 — 인라인 코드 스팬 + append-only 절 (D2·D7) ──────
# 언급(백틱 인용·사후 기록)은 통과시키고, 같은 문자열이 산문에 bare 로 있으면 그대로
# 잡는다. 면제 스팬은 step-2 의 펜스 제거 사본 위에서 계산한다.

# 1) 백틱으로 감싼 어휘·중괄호 표식이 통과한다
_bt_tok = GOOD.replace("- decision: local only", "- decision: 게이트는 `TBD` 표식을 잡는다")
assert validate(_bt_tok) == [], validate(_bt_tok)
_bt_brace = GOOD.replace("- decision: local only", "- decision: 템플릿 잔재는 `{여기 채우기}` 형태다")
assert validate(_bt_brace) == [], validate(_bt_brace)

# 2) 단정형 probe — 같은 문자열이 백틱 **밖**이면 반드시 FAIL
_bare_tok = GOOD.replace("- decision: local only", "- decision: 게이트는 TBD 표식을 잡는다")
assert any("placeholder marker" in e for e in validate(_bare_tok)), validate(_bare_tok)
_bare_brace = GOOD.replace("- decision: local only", "- decision: 템플릿 잔재는 {여기 채우기} 형태다")
assert any("template brace" in e for e in validate(_bare_brace)), validate(_bare_brace)

# 3) append-only 절(진행 로그·finding 큐)의 표식은 통과하고, 같은 줄이 본문 절이면 FAIL
_log_ok = GOOD + "\n## 진행 로그 (append-only)\n- step-1 에서 TBD 로 남겼던 값을 채웠다. {스코프} 표기도 정리.\n"
assert validate(_log_ok) == [], validate(_log_ok)
_fq_ok = GOOD + "\n## finding 큐\n- F9. TODO 주석이 남는 문제는 다음 milestone 후보.\n"
assert validate(_fq_ok) == [], validate(_fq_ok)
_body_hit = GOOD + "\n## 회고\n- step-1 에서 TBD 로 남겼던 값을 채웠다. {스코프} 표기도 정리.\n"
_body_errs = validate(_body_hit)
assert any("placeholder marker" in e for e in _body_errs), _body_errs
assert any("template brace" in e for e in _body_errs), _body_errs
# append-only 절은 다음 h2 에서 끝난다 — 그 아래 절은 면제가 아니다
_after_log = GOOD + "\n## 진행 로그\n- 기록.\n\n## 회고\n- TBD\n"
assert any("placeholder marker" in e for e in validate(_after_log)), validate(_after_log)

# 4) D7 — 거부 메시지가 그 자리에서 계약을 알려준다
assert any("백틱으로 감싼다" in e and "leaf 필드 값" in e for e in validate(_bare_tok)), validate(_bare_tok)

# 5) F1 재구성 fixture 2건 (M6 아카이브 계획서의 두 발생 형태) — 백틱으로 감싸면 통과
#    ① 검사를 설명하려고 어휘를 본문에 적음 ② 작성 제약을 설명하려고 중괄호 표식을 예시로 적음
_f1a = GOOD.replace("- decision: local only", "- decision: 미기입 검사는 `TODO` 같은 어휘를 계획서 전역에서 찾는다")
_f1b = GOOD.replace("- decision: local only", "- decision: step-3 은 `{모듈 이름}` 같은 표식을 남기면 안 된다")
assert validate(_f1a) == [], validate(_f1a)
assert validate(_f1b) == [], validate(_f1b)

# 6) 단정형 probe — 같은 문자열(백틱 없는 원형)을 leaf 필드 값으로 옮기면 반드시 FAIL
#    (리뷰 수리 후 필드 값 줄은 엄격 검사가 단독 소유 — 에러는 blank marker 1개)
_f1a_field = GOOD.replace("  - Artifact: runtime guard", "  - Artifact: 미기입 검사는 TODO 같은 어휘를 찾는다")
assert any("blank marker" in e for e in validate(_f1a_field)), validate(_f1a_field)
_f1b_field = GOOD.replace("  - Artifact: runtime guard", "  - Artifact: {모듈 이름} 구현")
assert any("blank marker" in e for e in validate(_f1b_field)), validate(_f1b_field)

print("plan gate M7 면제 표면 13건 PASS")

# ── M7 step-4: leaf 6필드 값 엄격 검사 (D3·D4) ────────────────────────────────
# 필드 값은 저자가 반드시 채우는 자리라 면제가 없다 — 백틱 안 표식도 잡고,
# 에러가 leaf 와 필드명을 지목한다. `Risk` 와 DoD 줄은 표면 밖.

# 1) 백틱으로 감싼 미채운 템플릿 표식을 leaf 필드 값에 넣으면 FAIL + leaf·필드 지목
_strict_brace = GRAPH_GOOD.replace("  - Artifact: runtime guard", "  - Artifact: `{모듈 이름}` 구현")
_sb_errs = validate(_strict_brace)
assert any("blank marker" in e and "Artifact" in e and "step-2" in e for e in _sb_errs), _sb_errs
# 단정형 probe ① — 면제가 필드 값까지 새면 M6 이 고친 구멍의 재생산이다
_strict_tok = GRAPH_GOOD.replace("  - Verify: test two", "  - Verify: `TBD`")
_st_errs = validate(_strict_tok)
assert any("blank marker" in e and "Verify" in e and "step-2" in e for e in _st_errs), _st_errs
# 필드용 어휘는 6종 전부다 — 전역에서 뺀 단어도 필드 값에서는 잡힌다 (D4 불변식)
_strict_ph = GRAPH_GOOD.replace("  - Artifact: runtime guard", "  - Artifact: placeholder")
assert any("blank marker" in e and "Artifact" in e for e in validate(_strict_ph)), validate(_strict_ph)

# 2) 백틱 안 정상 값(커맨드 등)은 통과한다
_strict_cmd = GRAPH_GOOD.replace("  - Verify: test two", "  - Verify: `python -m pytest -q scripts/`")
assert validate(_strict_cmd) == [], validate(_strict_cmd)

# 3) `Risk:` 는 엄격 표면 밖이다 — 근거 괄호의 백틱 표식 언급이 통과한다 (실증)
_risk_mention = RISK_GOOD.replace(
    "  - Risk: 위험 (통과하던 것이 막힌다)",
    "  - Risk: 위험 (게이트가 `{모듈 이름}` 표식 검사를 바꾼다)",
)
assert validate(_risk_mention) == [], validate(_risk_mention)

print("plan gate M7 필드 값 엄격 6건 PASS")

# ── M7 리뷰 수리: 필드 값의 bare 표식은 에러 **1개**만 낸다 ───────────────────
# 이중 발화는 힌트가 상충한다(전역: 백틱으로 감싸라 / 엄격: 백틱도 소용없다).
# 한 실수는 한 줄로 알린다 — parse_dependency_value 와 같은 규율.
_single = validate(GRAPH_GOOD.replace("  - Artifact: runtime guard", "  - Artifact: TBD 정리"))
_marker_errs = [e for e in _single if "TBD" in e]
assert len(_marker_errs) == 1, _marker_errs
assert "blank marker" in _marker_errs[0], _marker_errs
# 필드 밖 산문의 bare 표식은 여전히 전역 스캔이 잡는다 (스킵이 필드 줄로만 한정)
_still_global = validate(GRAPH_GOOD.replace("- decision: local only", "- decision: TBD"))
assert any("placeholder marker" in e for e in _still_global), _still_global

print("plan gate M7 이중 에러 수리 3건 PASS")

# ── M8 step-2: 발명 라벨 스캔도 언급 면제 위에서 돈다 (F4, 2026-08-21) ────────
# M7 리뷰 CONFIRMED: 백틱 인용·진행 로그 절 서술이 언급만으로 FAIL 했다.

# 1) 백틱 인용이 통과한다 (리뷰 재현 fixture ①)
_lbl_bt = GOOD.replace("- decision: local only", "- decision: `DP1` 같은 라벨은 금지다")
assert validate(_lbl_bt) == [], validate(_lbl_bt)
# 2) 진행 로그 절의 사후 서술이 통과한다 (리뷰 재현 fixture ②)
_lbl_log = GOOD + "\n## 진행 로그 (append-only)\n- DP2 라벨을 지웠다.\n"
assert validate(_lbl_log) == [], validate(_lbl_log)
# 3) 코드 펜스 안 라벨이 통과한다
_lbl_fence = GOOD + "\n```text\nDD-3 예시\n```\n"
assert validate(_lbl_fence) == [], validate(_lbl_fence)
# 4) 단정형 probe — 산문 bare 라벨은 반드시 FAIL (기존 케이스와 별도로 본문 절 위치)
_lbl_bare = GOOD + "\n## 회고\n- DP1 방식으로 정리했다.\n"
assert any("invented hierarchy label" in e for e in validate(_lbl_bare)), validate(_lbl_bare)
# 5) 여러 줄 코드 펜스 뒤 bare 라벨의 보고 줄 번호가 원문 줄 번호와 일치한다
_lbl_numbered = GOOD + "\n```json\n{\n  \"k\": 1\n}\n```\n- note: DP7 라벨\n"
_lbl_expected = _lbl_numbered[:_lbl_numbered.index("- note: DP7")].count("\n") + 1
_lbl_errs = validate(_lbl_numbered)
assert any(f"line {_lbl_expected}:" in e and "invented hierarchy" in e for e in _lbl_errs), (_lbl_expected, _lbl_errs)

print("plan gate M8 라벨 언급 면제 5건 PASS")

# ── M24: leaf heading 괄호 꼬리말 1개 + 생성일 게이팅 (2026-08-22, h-e M24) ──
# 실측 결함(h-e evidence/harness/2026-08-17-plan-gate-leaf-heading-tail.md):
# 완료 메모 꼬리말을 붙이면 leaf 미인식 — 의존이 가리키면 missing leaf, 안 가리키면
# 조용히 leaf 집합에서 빠진 채 PASS. 수정은 소급하지 않는다(코퍼스 26건 뒤집힘 실측).
from validate_plan_gate import leaf_headings  # noqa: E402

# 1) 발효일 이후 생성: 괄호 꼬리말 heading 이 leaf 로 인식되고 그래프·Risk 검증에 편입
TAIL_MODERN = RISK_GOOD.replace("> 생성: 2026-07-23", "> 생성: 2026-08-22").replace(
    "- [ ] **step-1 — validator**", "- [x] **step-1 — validator** (2026-08-22 완료)"
)
assert validate(TAIL_MODERN) == [], validate(TAIL_MODERN)
assert [m.group("id") for m in leaf_headings(TAIL_MODERN)] == ["step-1", "step-2"]

# 2) 소급 금지(negative — 게이팅이 뚫리면 여기서 FAIL): 발효일 이전 생성 문서의
#    꼬리말 heading 은 leaf 가 아니다 — 종전 판정과 동일하게 missing leaf 로 남는다.
TAIL_LEGACY = RISK_GOOD.replace(
    "- [ ] **step-1 — validator**", "- [x] **step-1 — validator** (완료 메모)"
)
assert [m.group("id") for m in leaf_headings(TAIL_LEGACY)] == ["step-2"], leaf_headings(TAIL_LEGACY)
assert any("missing leaf" in e for e in validate(TAIL_LEGACY)), validate(TAIL_LEGACY)

# 3) 생성일 줄 자체가 없는 구 plan 도 소급하지 않는다
TAIL_NODATE = GRAPH_GOOD.replace(
    "- [ ] **step-1 — validator**", "- [x] **step-1 — validator** (완료)"
)
assert [m.group("id") for m in leaf_headings(TAIL_NODATE)] == ["step-2"]

# 4) 허용은 괄호 1개뿐 — 괄호 2개는 발효일 이후에도 leaf 미인식 (heading-본문 경계 유지)
TAIL_TWO = TAIL_MODERN.replace("(2026-08-22 완료)", "(a) (b)")
assert [m.group("id") for m in leaf_headings(TAIL_TWO)] == ["step-2"]

# 5) 괄호 밖 산문 꼬리말도 leaf 미인식
TAIL_PROSE = TAIL_MODERN.replace("(2026-08-22 완료)", "완료했다")
assert [m.group("id") for m in leaf_headings(TAIL_PROSE)] == ["step-2"]

print("plan gate M24 leaf 꼬리말 5건 PASS")

# ── 되돌리기 어려운 동작 선언 (2026-08-29 h-e M28 O2 — 생성일 게이팅) ──────────
from validate_plan_gate import validate_destructive_declaration

# 1) 발효일 이후 생성 + 선언 줄 없음 → FAIL
NEW_PLAN = GOOD.replace("# Plan\n", "# Plan\n> 생성: 2026-08-29\n")
assert any("되돌리기 어려운 동작" in item for item in validate(NEW_PLAN))
# 2) 선언 줄(평문·굵게 둘 다)이 있으면 통과
assert validate(NEW_PLAN.replace("## Step Tree", "- 되돌리기 어려운 동작: 없음\n## Step Tree")) == []
assert validate(NEW_PLAN.replace("## Step Tree", "- **되돌리기 어려운 동작**: 라이브 배포 1건 — deploy_gate 정지\n## Step Tree")) == []
# 3) 발효일 이전 생성 → 기록 동결, 검사 안 함
OLD_PLAN = GOOD.replace("# Plan\n", "# Plan\n> 생성: 2026-08-28\n")
assert not any("되돌리기 어려운 동작" in item for item in validate(OLD_PLAN))
# 4) 생성일 줄 자체가 없는 구형 → 검사 안 함
assert validate_destructive_declaration(GOOD) == []

print("plan gate destructive 선언 4건 PASS")


# ── 2026-09-21 절차 다이어트: Risk 없음 leaf 는 Failure probe 면제 ───────────────
_STEP2_PROBE = "  - Failure probe: early stop fails\n"
assert any("Failure probe" in item for item in validate(GOOD.replace(_STEP2_PROBE, "  - Risk: 기계적 (게이트 집합 변동)\n"))), "기계적 leaf 는 여전히 필수"
assert not any("Failure probe" in item for item in validate(GOOD.replace(_STEP2_PROBE, "  - Risk: 없음 (기록만)\n"))), "없음 leaf 는 면제"


# ── M34 D5: Verify 가 주장한 경로의 실재 검사 (--pre-approval 에서만) ─────────────
from validate_plan_gate import validate_verify_targets, plan_repo_root, _verify_path_tokens

_TMP = Path(__file__).resolve().parent


def _verify(line_value: str, root: Path = _TMP, extra: str = "") -> list[str]:
    text = f"- [ ] **step-1 — x**\n  - Files: {extra}\n  - Verify: {line_value}\n"
    return validate_verify_targets(text, root)


# 1) 부재 경로는 ERROR
assert _verify("`pytest -q scripts/does_not_exist.py`"), "부재 경로를 놓쳤다"
# 2) Files 에 선언했으면 통과 — 이 step 이 만드는 파일이다
assert _verify("`pytest -q scripts/does_not_exist.py`", extra="`scripts/does_not_exist.py`(신설)") == []
# 3) 실재하면 통과
assert _verify("`python -m pytest validate_plan_gate.py`") == []
# 4) 경로 주장이 아닌 토큰은 무시한다 — URL·자리표시자·glob·rev:path·미지 변수
for benign in (
    "https://example.com/docs/guide.md",
    "`<계획서>/foo.md`",
    "`plans/*.md` 전건",
    "`git show HEAD:scripts/foo.py`",
    "`$OTHER_ROOT/foo.py`",
    "`pytest -q` 통과",
    "`plans/` 와 `archive/plans/`",
):
    assert _verify(benign) == [], benign
# 5) `$HARNESS_SCRIPTS/` 는 배포본으로 해석한다 (실재하는 기계장치 하나로 확인)
assert _verify("`python \"$HARNESS_SCRIPTS/validate_plan_gate.py\" x.md`") == []
assert _verify("`python \"$HARNESS_SCRIPTS/nope_does_not_exist.py\"`")
# 6) 한국어 계획서의 붙여쓰기 구분자(`A`·`B`, 소스↔`C`)를 토큰 경계로 가른다
assert _verify_path_tokens("소스↔`validate_plan_gate.py`·`nope/x.py` 대조") == ["nope/x.py"]
# 7) Failure probe 줄은 대상이 아니다 — 부재 경로를 일부러 적는 자리다
_PROBE_ONLY = "- [ ] **step-1 — x**\n  - Failure probe: `scripts/does_not_exist.py` 를 넣으면 ERROR\n"
assert validate_verify_targets(_PROBE_ONLY, _TMP) == []
# 8) 승인 후 모드에서는 꺼져 있다 (plan_path 없이 부르는 경로 포함)
_PLAN_BAD_VERIFY = GOOD.replace("  - Verify: test one\n", "  - Verify: `pytest -q scripts/does_not_exist.py`\n")
assert not any("실재하지 않는" in item for item in validate(_PLAN_BAD_VERIFY))
assert not any(
    "실재하지 않는" in item
    for item in validate(_PLAN_BAD_VERIFY, pre_approval=True)  # plan_path 없음 → 꺼짐
)
# 9) 레포 루트는 계획서에서 `.git` 을 찾아 올라가 잡는다
assert plan_repo_root(Path(__file__)) == Path(__file__).resolve().parents[3]

print("plan gate M34 Verify 실재 검사 9건 PASS")


# 10) 예외는 토큰 단위다 (2026-09-22) — 부분 문자열이면 다른 파일까지 면제됐다
#     ㉠ 상위 경로가 다른 동명 파일 — 옛 규칙에서 조용히 통과한 실결함
#     ㉡ 파일명 접미가 겹치는 이웃 파일 — 옛 규칙도 잡았다(회귀 방지)
assert _verify("`pytest -q scripts/nope.py`", extra="`other/scripts/nope.py`(신설)"), "상위 경로가 달라도 면제됐다"
assert _verify("`pytest -q scripts/nope.py`", extra="`scripts/bar_nope.py`(신설)"), "이름 접미만 겹쳐도 면제됐다"
#     ㉢ 같은 파일을 `$HARNESS_ROOT/` 로 적어도 같은 것으로 본다
assert _verify("`pytest -q scripts/nope.py`", extra="`$HARNESS_ROOT/scripts/nope.py`(신설)") == []

print("plan gate Files 예외 토큰 대조 3건 PASS")



# ── 수치 출처 검사가 changeset 디렉터리명을 수치로 오인하지 않는다 ──────────
# 2026-09-22 스테이징 스모크 관측: DoD 문장에 `changesets/20260922-slug` 를 쓰자
# 게이트가 `20260922` 를 "출처 없는 수치"로 잡아 FAIL 했다. 압축 날짜는 식별자다.
import validate_plan_gate as _vpg


def _dod_plan(dod_line: str) -> str:
    return f"> 생성: 2026-09-22\n\n- DoD: {dod_line}\n"


def test_compact_date_in_changeset_path_is_not_a_measurement():
    errs = _vpg.validate_measurement_provenance(
        _dod_plan("`changesets/20260922-foo-bar/README.md` 에 한 줄을 남긴다"))
    assert errs == [], errs


def test_hyphenated_date_is_still_not_a_measurement():
    errs = _vpg.validate_measurement_provenance(_dod_plan("2026-09-22 까지 닫는다"))
    assert errs == []


def test_real_measurement_still_requires_provenance():
    """오탐을 고치면서 진짜 검사를 죽이지 않았는지 — 양방향 계약."""
    errs = _vpg.validate_measurement_provenance(_dod_plan("테스트 93건이 green 이다"))
    assert len(errs) == 1 and "수치 출처" in errs[0]


def test_bare_eight_digit_number_is_still_checked():
    """하이픈이 안 붙은 8자리는 날짜 경로가 아니다 — 계속 수치로 본다."""
    errs = _vpg.validate_measurement_provenance(_dod_plan("처리량 20260922 건을 넘긴다"))
    assert len(errs) == 1


# 2026-09-30 (r6-plan-methodology R1): 코어 3 은 선택 — 자기선언 도메인 + 검토 후 제외만으로 PASS,
# 적혀 있는데 비어 있으면 여전히 FAIL.
from validate_plan_gate import validate_scaffold  # noqa: E402


def test_scaffold_core_three_optional():
    domain_only = "## 스캐폴딩 결정\n- 데이터: 스키마 v3 유지 — step-2 가 바뀜\n- 검토 후 제외: 디자인 — 화면 없음\n"
    assert validate_scaffold(domain_only) == []
    empty_core = domain_only + "- 검증: \n"
    assert any("present but empty" in e for e in validate_scaffold(empty_core))


# ── M26 step-3 (2026-11-18): 갈래 목록 절 검사 + 격리 worktree 배차 행 거부 ─────────
# 생성일 2026-11-18 이후 계획서만 — 옛 계획서의 승인 해시를 깨지 않는다(소급 없음).
# 행 문법: `- <갈래 id> · <제목> · 완료 기준: <한 줄> · 소유: <경로·글롭 쉼표 목록>`
_FAN_BASE = _P30.replace("> 생성: 2026-09-30", "> 생성: 2026-11-18").replace("격리 worktree", "격리 none")
_FAN_TWO = (
    "## 갈래 목록\n"
    "- 펼침 판정: 펼침 — 갈래 둘 · 소유를 가를 수 있다 · 사용자가 갈래에서 말할 일이 있다\n"
    "- gate · 계획 게이트 · 완료 기준: 갈래 목록 절 검사가 FAIL/PASS 를 가른다 · 소유: scripts/gate.py, scripts/test_gate.py\n"
    "- close · 갈래 마감 · 완료 기준: 상태 파일을 쓰지 않고 닫는다 · 소유: scripts/close.py, docs/close/**\n"
)


def _fan_plan(section: str, base: str = _FAN_BASE) -> str:
    return base.replace("## 스캐폴딩 결정", section + "## 스캐폴딩 결정", 1)


def test_fanout_base_without_section_passes():
    assert validate(_FAN_BASE) == []


def test_fanout_section_valid_passes():
    plan = _fan_plan(_FAN_TWO)
    assert validate(plan) == []
    # 절 검사기가 실제로 이 절을 읽었다 — 갈래 둘, 판정 줄은 행이 아니다
    assert _vpg.parse_fanout_rows(plan) == [
        ("gate", "계획 게이트", "갈래 목록 절 검사가 FAIL/PASS 를 가른다", ["scripts/gate.py", "scripts/test_gate.py"]),
        ("close", "갈래 마감", "상태 파일을 쓰지 않고 닫는다", ["scripts/close.py", "docs/close/**"]),
    ]
    assert _vpg.validate_fanout(plan) == []


def test_old_plan_with_worktree_isolation_still_passes():
    # 생성일 2026-09-30 — `격리 worktree` 행 그대로 PASS
    assert "격리 worktree" in _P30
    assert validate(_P30) == []
    # 생성일이 없어도 새 규칙은 안 걸린다
    nodate = _P30.replace("> 생성: 2026-09-30\n", "")
    assert not any("worktree" in e for e in validate(nodate))
    # 옛 계획서에 깨진 갈래 목록이 있어도 검사하지 않는다(소급 없음)
    broken = _fan_plan("## 갈래 목록\n- A · 한 갈래뿐\n", base=_P30)
    assert not any("갈래" in e for e in validate(broken))
    # 경계: 생성일 2026-11-17 은 옛 계획서
    assert validate(_P30.replace("> 생성: 2026-09-30", "> 생성: 2026-11-17")) == []


def test_new_plan_worktree_isolation_fails():
    plan = _FAN_BASE.replace(
        "- step-2 · worker(sonnet) · 격리 none · 검증 pytest a",
        "- step-2 · worker(sonnet) · 격리 worktree · 검증 pytest a",
    )
    errs = validate(plan)
    assert any("격리 worktree" in e and "step-2" in e for e in errs), errs
    assert len([e for e in errs if "격리 worktree" in e]) == 1, errs


def test_prose_mentioning_worktree_does_not_fail():
    # 배차 행이 아닌 본문 문장 속 글자는 검사 대상이 아니다
    plan = _FAN_BASE.replace(
        "## 스캐폴딩 결정",
        "## 메모\n- 옛 배차표의 `격리 worktree` 행은 은퇴했다. 격리 worktree 라는 말은 여기서 설명일 뿐이다\n## 스캐폴딩 결정",
        1,
    )
    assert validate(plan) == []


def test_fanout_overlapping_owns_fails():
    same = _FAN_TWO.replace("docs/close/**", "scripts/gate.py")
    errs = validate(_fan_plan(same))
    assert any("소유가 겹친다" in e and "gate" in e and "close" in e and "scripts/gate.py" in e for e in errs), errs
    # 한 항목이 다른 항목의 접두 경로
    prefix = _FAN_TWO.replace("docs/close/**", "scripts")
    errs = validate(_fan_plan(prefix))
    assert any("소유가 겹친다" in e for e in errs), errs
    # 글롭 디렉터리 접두
    glob = _FAN_TWO.replace("scripts/gate.py, scripts/test_gate.py", "scripts/**").replace(
        "scripts/close.py", "scripts/close.py"
    )
    errs = validate(_fan_plan(glob))
    assert any("소유가 겹친다" in e for e in errs), errs
    # 이름만 비슷한 형제 경로는 겹침이 아니다
    sibling = _FAN_TWO.replace("scripts/gate.py", "scripts/gate").replace("scripts/close.py", "scripts/gate_close.py")
    assert validate(_fan_plan(sibling)) == []


def _own_pair(a: str, b: str) -> str:
    return (
        "## 갈래 목록\n"
        f"- gate · 계획 게이트 · 완료 기준: 검사가 돈다 · 소유: {a}\n"
        f"- close · 갈래 마감 · 완료 기준: 닫는다 · 소유: {b}\n"
    )


def test_fanout_repo_wide_and_glob_owns_overlap():
    for a, b in [
        ("**", "scripts/x.py"),
        ("*", "scripts/x.py"),
        (".", "scripts/x.py"),
        ("./", "scripts/x.py"),
        ("src/*.py", "src/a.py"),
        ("*.md", "docs/x.md"),
        ("docs/x.md", "**"),
    ]:
        errs = _vpg.validate_fanout(_fan_plan(_own_pair(a, b)))
        assert any("소유가 겹친다" in e for e in errs), (a, b, errs)
    # 겹치지 않는 쪽
    assert _vpg.validate_fanout(_fan_plan(_own_pair("src/a/**", "src/b.py"))) == []
    assert _vpg.validate_fanout(_fan_plan(_own_pair("src/*.py", "docs/x.md"))) == []


def test_fanout_fewer_than_two_fails():
    one = "## 갈래 목록\n- gate · 계획 게이트 · 완료 기준: 검사가 돈다 · 소유: scripts/gate.py\n"
    errs = validate(_fan_plan(one))
    assert any("갈래가 둘 미만" in e for e in errs), errs
    errs = validate(_fan_plan("## 갈래 목록\n"))
    assert any("갈래가 둘 미만" in e for e in errs), errs


def test_fanout_row_grammar_fails():
    # 갈래 id 대문자
    errs = validate(_fan_plan(_FAN_TWO.replace("- gate ·", "- Gate ·")))
    assert any("갈래 행이 문법 밖" in e for e in errs), errs
    # 소유 칸 누락
    errs = validate(_fan_plan(_FAN_TWO.replace(" · 소유: scripts/gate.py, scripts/test_gate.py", "")))
    assert any("갈래 행이 문법 밖" in e for e in errs), errs
    # 완료 기준 비어 있음
    errs = validate(_fan_plan(_FAN_TWO.replace("완료 기준: 갈래 목록 절 검사가 FAIL/PASS 를 가른다", "완료 기준:")))
    assert any("갈래 행이 문법 밖" in e for e in errs), errs
    # 같은 갈래 id 두 번
    errs = validate(_fan_plan(_FAN_TWO.replace("- close ·", "- gate ·")))
    assert any("갈래 id 중복" in e and "gate" in e for e in errs), errs
