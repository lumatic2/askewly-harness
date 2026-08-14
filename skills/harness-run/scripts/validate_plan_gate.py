#!/usr/bin/env python3
"""Validate the harness produce-to-run gate for a multi-step plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# 승인은 Status 값의 **머리**에서 읽는다 (2026-07-23 DC1 R1). 구현은 `\b(approved|completed)\b`
# 였는데, 그러면 "승인 대기 — 승인 시 approved 로 갱신" 같은 *산문 언급*도 승인으로 읽힌다
# (실측: 미승인 계획 5건이 전부 PASS 했다). 같은 뿌리의 결함을 OI3 `guard_wired` 도 겪었다 —
# 이름이 나온다고 배선된 게 아니다. 승인 도장은 줄 맨 앞에 찍히므로 머리만 본다.
APPROVED = re.compile(r"^\s*\**\s*(approved|completed)\b", re.I)
UNAPPROVED = re.compile(r"awaiting\s+run\s+approval|proposed|draft|승인\s*대기|초안", re.I)
# CF3 step-4 (2026-07-21): 게이트가 사람의 평범한 마크다운을 거부하면 안 된다.
# `## 결정 로그 (사전 소진)` 처럼 제목에 부연을 달거나 `- **execution mode**:` 처럼
# 굵게 쓰는 건 일반적인 표기인데 전부 FAIL 이었다 — 정본 템플릿조차 자기 게이트를
# 통과 못 했고(CF1 finding F1), 세션마다 형식을 역추적하느라 시간을 썼다.
# 선언의 *존재*는 그대로 요구하고 표기 흔들림만 수용한다.
DECISION_HEADING = re.compile(r"^##\s+(?:결정 로그|Decision Log)\b.*$", re.M | re.I)
DECISION_STATUS = re.compile(r"^\s*-\s*status:\s*(resolved|none-required)\s*$", re.M | re.I)
UNRESOLVED = re.compile(r"^\s*-\s*(?:status:\s*unresolved|unresolved:|pending-decision:|미해결:|결정 필요:)", re.M | re.I)
PLACEHOLDER = re.compile(r"\b(?:TBD|TODO|FIXME|PLACEHOLDER|미정|추후\s*결정)\b", re.I)
# IMP-041 (superpowers writing-plans 이식): 템플릿 중괄호 잔재 — `{여기 채우기}` 류.
# 코드 펜스 밖에서만 검사한다 (plan 내 코드/JSON 예시 오탐 방지).
BRACE_PLACEHOLDER = re.compile(r"\{(?:\.{3}|[A-Za-z가-힣][A-Za-z가-힣 _/-]{0,30})\}")
CODE_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
# 용어 사전 lint (2026-07-17): 위계 레벨 예약어(Horizon/Milestone/Step) 대신 세션이 발명한
# DP1·DD-3 식 라벨 금지 (harness-plan 용어 사전). 좁은 패턴만 — 일반 약어 오탐 방지.
FORBIDDEN_LEVEL_LABEL = re.compile(r"\b(?:DP|DD)[-–]?\d+\b")
VERIFY_LINE = re.compile(r"^[ \t]*-[ \t]*(?:Verify|검증|Acceptance Criteria)[ \t]*:[ \t]*(.*)$", re.M | re.I)
SUPERSEDES = re.compile(r"^Supersedes:[ \t]*(.*)$", re.M | re.I)
EXECUTION_MODE = re.compile(r"^\s*-\s*\*{0,2}(?:Execution mode|실행 모드|execution mode)\*{0,2}\s*:\s*`?continuous`?\s*$", re.M | re.I)
STOP_POLICY = re.compile(r"(?:Stop only|중단점|stop points).*\b(?:blocked|decision_required|risk_gate)\b", re.I)
ROLLBACK = re.compile(r"^[ \t]*-[ \t]*\*{0,2}(?:Rollback/cleanup|rollback/cleanup|롤백/정리)\*{0,2}[ \t]*:[ \t]*(.*)$", re.M | re.I)
# CS1 step-2 (2026-07-17): 스캐폴딩 결정 완전성 — 작업 유형별 필수 도메인 기계 검증
WORK_TYPE_RE = re.compile(r"^[ \t]*-[ \t]*작업 유형[ \t]*:[ \t]*(\S+)", re.M)
SCAFFOLD_HEADING_RE = re.compile(r"^##[ \t]+스캐폴딩 결정.*$", re.M)
WORK_TYPES = {"product-service", "tooling", "workflow", "learning", "analysis"}
SCAFFOLD_DOMAINS = {
    "product-service": ["frontend", "backend", "data", "design", "deploy", "관측"],
    # 축소 셋 (tooling/workflow/learning/analysis 공통)
    "_reduced": ["source-of-truth", "deploy", "테스트 표면"],
}
LEAF_FIELDS = {
    "Artifact": re.compile(r"^[ \t]*-[ \t]*(?:Artifact|산출물)[ \t]*:[ \t]*(.*)$", re.M | re.I),
    "Files": re.compile(r"^[ \t]*-[ \t]*(?:Files|파일|Surfaces)[ \t]*:[ \t]*(.*)$", re.M | re.I),
    "Dependencies": re.compile(r"^[ \t]*-[ \t]*(?:Dependencies|의존성)[ \t]*:[ \t]*(.*)$", re.M | re.I),
    "Verify": VERIFY_LINE,
    "Failure probe": re.compile(r"^[ \t]*-[ \t]*(?:Failure probe|실패 검증|Negative probe)[ \t]*:[ \t]*(.*)$", re.M | re.I),
    "Commit": re.compile(r"^[ \t]*-[ \t]*(?:Commit|커밋 경계)[ \t]*:[ \t]*(.*)$", re.M | re.I),
}
# id-based leaf heading (PLAN_TEMPLATE.md '- [ ] **step-1 — slug**' form). Graph
# validation only runs for leaves written this way — plans using the older plain
# '- [ ] Step 1' style skip the graph check silently rather than being forced to
# migrate. This does not touch task-master's complexity score, which stays out of
# scope (see TASK_MASTER_STYLE fixture in the test file): only edge validity on
# top of the *existing* mandatory verify contract above.
LEAF_ID_HEADING = re.compile(
    r"^- \[(?: |x|X)\]\s+\*\*(?P<id>[\w.-]+)\s*(?:—|--|-)\s*(?P<slug>.+?)\*\*\s*$", re.M
)


# CS6 step-2 (2026-07-17): 범용화 — 코어 3(별칭 허용) + 자기선언 도메인 + 제외 자기점검.
# 구 "작업 유형 enum + 고정 도메인" plan 은 legacy 모드로 그대로 PASS (하위호환 자동 감지).
CORE_DOMAINS = {
    "source-of-truth": ["source-of-truth", "정본"],
    "검증": ["검증", "검증 표면", "테스트 표면", "테스트"],
    "배포/운영": ["배포/운영", "deploy", "배포", "운영"],
}
EXCLUDE_LINE = re.compile(r"^[ \t]*-[ \t]*검토 후 제외[ \t]*:[ \t]*(.*)$", re.M)
BULLET_LINE = re.compile(r"^[ \t]*-[ \t]*([^:\n]{1,40})[ \t]*:[ \t]*(.*)$", re.M)


def _needs_reason(errors: list[str], domain: str, value: str) -> None:
    if re.fullmatch(r"해당 없음[.。]?", value.strip()):
        errors.append(f"scaffolding decision '해당 없음' needs a reason (— <이유>): {domain}")


def validate_scaffold(text: str) -> list[str]:
    """스캐폴딩 결정 완전성: 신형 = 코어 3 + 자기선언 전부 채움 + 제외 자기점검 / 구형 = 유형별 고정 도메인."""
    errors: list[str] = []
    heading = SCAFFOLD_HEADING_RE.search(text)
    if heading is None:
        errors.append("plan must contain a ## 스캐폴딩 결정 section")
        return errors
    tail = text[heading.end():]
    section = re.split(r"^##\s+", tail, maxsplit=1, flags=re.M)[0]

    type_match = WORK_TYPE_RE.search(section)
    work_type = type_match.group(1).strip() if type_match else None
    if work_type in WORK_TYPES:
        # legacy 모드 (CS1 규칙 그대로 — 기존 승인 plan 하위호환)
        domains = SCAFFOLD_DOMAINS["product-service"] if work_type == "product-service" else SCAFFOLD_DOMAINS["_reduced"]
        for domain in domains:
            line = re.search(rf"^[ \t]*-[ \t]*{re.escape(domain)}[ \t]*:[ \t]*(.*)$", section, re.M)
            if line is None or not line.group(1).strip():
                errors.append(f"scaffolding decision missing or empty: {domain} ({work_type})")
                continue
            _needs_reason(errors, domain, line.group(1))
        return errors

    # 신형 (범용) 모드 — 유형 선언 불요, 코어 3 필수
    for core, aliases in CORE_DOMAINS.items():
        line = None
        for alias in aliases:
            line = re.search(rf"^[ \t]*-[ \t]*{re.escape(alias)}[ \t]*:[ \t]*(.*)$", section, re.M)
            if line:
                break
        if line is None or not line.group(1).strip():
            errors.append(f"scaffolding core domain missing or empty: {core} (별칭: {'/'.join(aliases)})")
            continue
        _needs_reason(errors, core, line.group(1))
    # 자기선언 도메인 전부 채움 (섹션 안 모든 `- name:` bullet)
    for m in BULLET_LINE.finditer(section):
        name, value = m.group(1).strip(), m.group(2).strip()
        if name == "검토 후 제외":
            continue
        if not value:
            errors.append(f"self-declared scaffolding domain is empty: {name}")
        else:
            _needs_reason(errors, name, value)
    # 제외 자기점검 1줄 의무 (누락 vs 의도적 제외 구분)
    excl = EXCLUDE_LINE.search(section)
    if excl is None or not excl.group(1).strip():
        errors.append("scaffolding section must declare '- 검토 후 제외: <표준 도메인 — 이유>' (없으면 '없음')")
    return errors


# 의존 값 문법 (2026-07-23 OI2 step-1 실측 확정 — 문법 정본은 PLAN_TEMPLATE step 트리 머리말).
#   none | 없음 | step-N 나열(쉼표/공백) [+ 괄호 꼬리말 1개로 *왜*]
# 꼬리 괄호를 허용하는 이유: 21개 plan 이 이미 그렇게 쓰고 있고 그 괄호가 의존의 근거를 담는다.
_DEP_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")
_DEP_NONE_RE = re.compile(r"^(?:none|없음|-)\b[\s.]*$", re.I)
# 다른 milestone 의 step 을 가리키는 형태(`CS1 step-1`·`LA1·LA2 완료`). 실측 2건.
_CROSS_MILESTONE_RE = re.compile(r"\b[A-Z]{1,4}\d+\b")


def parse_dependency_value(raw: str) -> tuple[list[str], str | None]:
    """(ids, error). 파싱 실패는 **한 줄로** 알린다.

    구 구현은 산문을 공백으로 쪼개 토큰마다 'missing leaf' 를 냈다 — 한 줄 실수가
    오류 4~12개로 번져 무엇이 문제인지 안 보였다(실측: 10개 plan 에서 123건).
    dryforge `go/SKILL.md:143` 의 규율 — 어느 검사가 어디서 실패했는지 지목한다.
    """
    value = (raw or "").strip()
    tail = _DEP_TAIL_RE.search(value)
    if tail:
        value = value[: tail.start()].strip()
    if not value or _DEP_NONE_RE.match(value):
        return [], None
    tokens = [t for t in re.split(r"[,\s]+", value) if t]
    ids = [t for t in tokens if re.fullmatch(r"step-\d+", t)]
    stray = [t for t in tokens if not re.fullmatch(r"step-\d+", t)]
    if stray:
        if any(_CROSS_MILESTONE_RE.search(t) for t in stray):
            return [], (
                f"Dependencies 가 다른 milestone 을 가리킨다 ({' '.join(stray)}) — "
                "milestone 사이의 순서는 ROADMAP marker 가 소유한다. "
                "이 필드에는 같은 plan 안의 `step-N` 만 적는다"
            )
        return [], (
            f"Dependencies 값이 문법 밖이다 ({' '.join(stray)}) — "
            "`none` 또는 `step-N` 나열만 쓴다(이유는 끝에 괄호 하나로)"
        )
    return ids, None


def _parse_leaf_dependencies(body: str) -> list[str]:
    match = LEAF_FIELDS["Dependencies"].search(body)
    if not match:
        return []
    ids, _err = parse_dependency_value(match.group(1))
    return ids


def validate_graph(text: str) -> list[str]:
    """Dependency-graph edge validity for id-based leaves (missing/self/duplicate/cycle/no
    independent root) — adopted from plan-forge (2026-07-20) on top of the existing
    per-leaf verify contract. Silently no-ops for plans that don't use the
    '- [ ] **id — slug**' heading form, so it never forces a migration."""
    matches = list(LEAF_ID_HEADING.finditer(text))
    if not matches:
        return []

    leaves: dict[str, str] = {}
    order: list[str] = []
    for i, m in enumerate(matches):
        leaf_id = m.group("id")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        h2 = re.search(r"^## ", text[start:end], re.M)
        if h2:
            end = start + h2.start()
        leaves[leaf_id] = text[start:end]
        order.append(leaf_id)

    errors: list[str] = []
    ids = set(leaves.keys())
    edges: dict[str, list[str]] = {}
    for leaf_id, body in leaves.items():
        dep_match = LEAF_FIELDS["Dependencies"].search(body)
        deps, syntax_error = parse_dependency_value(dep_match.group(1) if dep_match else "")
        if syntax_error:
            errors.append(f"leaf {leaf_id}: {syntax_error}")
        seen: set[str] = set()
        clean: list[str] = []
        for dep in deps:
            if dep == leaf_id:
                errors.append(f"leaf {leaf_id} depends on itself")
                continue
            if dep not in ids:
                errors.append(f"leaf {leaf_id} depends on missing leaf: {dep}")
                continue
            if dep in seen:
                errors.append(f"leaf {leaf_id} has duplicate dependency: {dep}")
                continue
            seen.add(dep)
            clean.append(dep)
        edges[leaf_id] = clean

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {leaf_id: WHITE for leaf_id in ids}

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for dep in edges.get(node, []):
            if color.get(dep) == GRAY:
                cycle_start = path.index(dep)
                cycle = " -> ".join(path[cycle_start:] + [dep])
                errors.append(f"dependency cycle detected: {cycle}")
            elif color.get(dep) == WHITE:
                dfs(dep, path)
        path.pop()
        color[node] = BLACK

    for leaf_id in order:
        if color[leaf_id] == WHITE:
            dfs(leaf_id, [])

    if edges and not any(len(deps) == 0 for deps in edges.values()):
        errors.append("no independent root leaf: every leaf declares at least one dependency")

    return errors


# ── 위험 등급 (2026-07-23 DC1 step-2) ────────────────────────────────────────
# 등급이 배차(직접 수행 vs 위임)와 검증 두께를 정한다. 가르는 질문 하나: **이 변경으로
# 지금까지 통과하던 것이 막히기 시작하는가.** 시작하면 `위험`, 막히는 집합이 그대로면
# `기계적`, 산출물이 기록뿐이면 `없음`.
#
# DC1 step-1 실측이 이 문장을 강제했다: 같은 leaf 를 두 판정자가 분류했더니 12건 중 8건만
# 일치했고(66.7%), 불일치 4건이 **전부** 위험↔기계적 경계였다. 경계를 말로만 두면 등급이
# 판정자마다 흔들리고, 그 위에 세운 배차 규칙도 같이 흔들린다.
#
# 범위는 **발효일 이후 생성된 plan 의 id 형식 leaf**다. 처음엔 "id 형식이면 신형"으로 잡았는데
# 계획의 반대 프로브가 그 자리에서 뒤집었다 — `plans/2026-07-21-mm3-eol-encoding.md` 같은
# 이미 승인된 계획도 id 형식이라 leaf 3개가 통째로 FAIL 났다. id 형식은 *새 계획*의 대리
# 지표가 아니다. 그래서 `validate_measurement_provenance` 의 선례대로 생성일로 가른다
# (기록은 동결이 원칙 — 문서 수명 규약).
RISK_RULE_SINCE = "2026-07-23"
RISK_VALUES = ("위험", "기계적", "없음", "미분류")
# LEAF_FIELDS 에 넣지 않는다 — 그 표는 *모든* leaf 에 필수라 구 형식 plan 까지 소급 FAIL 난다.
RISK_FIELD_RE = re.compile(r"^[ \t]*-[ \t]*(?:Risk|위험 등급)[ \t]*:[ \t]*(.*)$", re.M | re.I)
_RISK_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def parse_risk_value(raw: str) -> tuple[str | None, str | None]:
    """→ (등급, error). 값 뒤 괄호 꼬리말 1개는 근거라서 허용한다."""
    value = _RISK_TAIL_RE.sub("", (raw or "").strip()).strip()
    if not value:
        return None, "Risk 값이 비었다"
    if value not in RISK_VALUES:
        return None, (
            f"Risk 값이 어휘 밖이다 ({value}) — {'|'.join(RISK_VALUES)} 중 하나를 쓴다"
            "(근거는 끝에 괄호 하나로)"
        )
    return value, None


def validate_risk(text: str) -> tuple[list[str], dict[str, int]]:
    """→ (errors, 등급별 집계). 미분류는 통과시키되 따로 센다 — 게이트가 미분류로
    도피하는지 관측할 수 있어야 등급이 장식이 되지 않는다."""
    created = re.search(r"^>\s*생성:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if created is None or created.group(1) < RISK_RULE_SINCE:
        return [], {}
    matches = list(LEAF_ID_HEADING.finditer(text))
    if not matches:
        return [], {}
    errors: list[str] = []
    tally: dict[str, int] = {}
    for i, m in enumerate(matches):
        leaf_id = m.group("id")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        h2 = re.search(r"^## ", text[start:end], re.M)
        if h2:
            end = start + h2.start()
        hit = RISK_FIELD_RE.search(text[start:end])
        if hit is None:
            errors.append(
                f"leaf {leaf_id}: Risk 선언이 없다 — {'|'.join(RISK_VALUES)} 중 하나를 적는다"
                "(가르는 질문: 이 변경으로 지금까지 통과하던 것이 막히기 시작하는가)"
            )
            continue
        value, err = parse_risk_value(hit.group(1))
        if err:
            errors.append(f"leaf {leaf_id}: {err}")
            continue
        tally[value] = tally.get(value, 0) + 1
    return errors, tally


# ── wave 파생 (2026-07-23 OI2 step-3) ────────────────────────────────────────
# 그래프가 있으면 **다음에 착수 가능한 leaf 집합**이 파생된다. 이 함수는 판정하지 않고
# 계산만 한다 — 소비자는 이어받기 훅(`harness_work_state`)과 이 게이트의 정보 출력이다.
_PATH_RE = re.compile(r"[\w./\\-]*[\w-]+\.(?:py|sh|md|json|jsonl|ya?ml|toml|ts|tsx|js)\b")


def _leaf_files(body: str) -> set[str]:
    """`Files:` 에서 경로처럼 보이는 것만 뽑는다.

    자연어 필드라 정확할 수 없다. **못 뽑으면 빈 집합**이고, 빈 집합은 아래에서
    '겹칠 수 있음' 으로 처리된다 — 병렬을 낙관하다 충돌시키는 것보다 순차가 안전하다.
    """
    match = LEAF_FIELDS.get("Files")
    if match is None:
        return set()
    hit = match.search(body)
    if not hit:
        return set()
    return {p.replace("\\", "/").lstrip("`") for p in _PATH_RE.findall(hit.group(1))}


def derive_waves(text: str) -> list[list[str]]:
    """의존을 위상정렬해 동시 착수 가능한 집합들로 나눈다.

    같은 파일을 건드리는 leaf 는 **같은 wave 에 두지 않는다**(격리 없이 병렬하면 충돌).
    `Files:` 에서 경로를 못 뽑은 leaf 도 겹칠 수 있는 것으로 본다 — 안전 측.
    그래프가 없거나 깨졌으면 빈 목록(= 소비자는 텍스트 순서로 폴백).
    """
    matches = list(LEAF_ID_HEADING.finditer(text))
    if not matches:
        return []
    bodies: dict[str, str] = {}
    order: list[str] = []
    for i, m in enumerate(matches):
        start, end = m.end(), (matches[i + 1].start() if i + 1 < len(matches) else len(text))
        h2 = re.search(r"^## ", text[start:end], re.M)
        if h2:
            end = start + h2.start()
        bodies[m.group("id")] = text[start:end]
        order.append(m.group("id"))

    edges, files = {}, {}
    for leaf_id, body in bodies.items():
        dep_match = LEAF_FIELDS["Dependencies"].search(body)
        ids, err = parse_dependency_value(dep_match.group(1) if dep_match else "")
        if err:
            return []
        edges[leaf_id] = [d for d in ids if d in bodies and d != leaf_id]
        files[leaf_id] = _leaf_files(body)

    waves: list[list[str]] = []
    done: set[str] = set()
    while len(done) < len(order):
        ready = [i for i in order if i not in done and all(d in done for d in edges[i])]
        if not ready:
            return []  # 순환 — validate_graph 가 이미 오류로 보고했다
        wave: list[str] = []
        claimed: set[str] = set()
        for leaf_id in ready:
            touched = files[leaf_id]
            if wave and (not touched or touched & claimed):
                continue  # 파일이 겹치거나 알 수 없다 → 다음 wave 로
            wave.append(leaf_id)
            claimed |= touched
        done |= set(wave)
        waves.append(wave)
    return waves


# ── 배차 설계 (2026-08-14 M18 step-1) ────────────────────────────────────────
# 선택(opt-in) 절 — 절이 없으면 무검사(기존 계획 무영향). 있으면 문법·실재·모순을 검사한다.
# 행 문법: `- step-N · inline|worker(<model>) · 격리 none|worktree · 검증 <경로/커맨드>`
# 근거 줄: `- 근거: <배차 이득 — 파일 격리|독립 시각|컨텍스트 격리|벽시계 단축 중 ≥1>`
# 배차 이득·워커/검증자 계약의 정본은 delegation.md — 여기는 문법과 그래프 모순만 본다.
DISPATCH_HEADING_RE = re.compile(r"^##[ \t]+배차 설계.*$", re.M)
DISPATCH_ROW_RE = re.compile(
    r"^[ \t]*-[ \t]*(?P<id>step-\d+)[ \t]*·[ \t]*(?P<mode>inline|worker\((?P<model>[^)]*)\))"
    r"[ \t]*·[ \t]*격리[ \t]+(?P<iso>none|worktree)[ \t]*·[ \t]*검증[ \t]+(?P<verify>.+)$"
)
DISPATCH_STEP_BULLET_RE = re.compile(r"^[ \t]*-[ \t]*step-\d+\b.*$", re.M)
DISPATCH_GAIN_RE = re.compile(r"^[ \t]*-[ \t]*근거[ \t]*:[ \t]*(.*)$", re.M)
DISPATCH_GAINS = ("파일 격리", "독립 시각", "컨텍스트 격리", "벽시계 단축")


def _leaf_dependency_edges(text: str) -> dict[str, list[str]]:
    """id 형식 leaf 의 (id → 의존 id 목록). validate_graph 와 같은 절단 규칙."""
    matches = list(LEAF_ID_HEADING.finditer(text))
    edges: dict[str, list[str]] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        h2 = re.search(r"^## ", text[start:end], re.M)
        if h2:
            end = start + h2.start()
        dep = LEAF_FIELDS["Dependencies"].search(text[start:end])
        ids, _err = parse_dependency_value(dep.group(1) if dep else "")
        edges[m.group("id")] = ids
    return edges


def validate_dispatch(text: str) -> list[str]:
    heading = DISPATCH_HEADING_RE.search(text)
    if heading is None:
        return []
    errors: list[str] = []
    tail = text[heading.end():]
    section = re.split(r"^##\s+", tail, maxsplit=1, flags=re.M)[0]
    leaf_ids = {m.group("id") for m in LEAF_ID_HEADING.finditer(text)}
    rows: dict[str, re.Match] = {}
    for line_m in DISPATCH_STEP_BULLET_RE.finditer(section):
        line = line_m.group(0)
        m = DISPATCH_ROW_RE.match(line)
        if not m:
            errors.append(
                f"배차 행이 문법 밖이다: {line.strip()[:70]} — "
                "`- step-N · inline|worker(<model>) · 격리 none|worktree · 검증 <경로>`"
            )
            continue
        sid = m.group("id")
        if m.group("mode").startswith("worker") and not (m.group("model") or "").strip():
            errors.append(f"배차 행 {sid}: worker 에 model 이 없다 — worker(<model>) 로 명시한다")
        if sid not in leaf_ids:
            errors.append(f"배차 행이 실재하지 않는 leaf 를 가리킨다: {sid}")
        if sid in rows:
            errors.append(f"배차 행 중복: {sid}")
        rows[sid] = m
    if not rows and not errors:
        errors.append("배차 설계 절에 배차 행이 없다 — 절을 지우거나 행을 적는다")
    gain = DISPATCH_GAIN_RE.search(section)
    if gain is None or not any(g in gain.group(1) for g in DISPATCH_GAINS):
        errors.append(
            "배차 설계 절에 배차 이득 `- 근거:` 줄이 없다 — "
            f"{'|'.join(DISPATCH_GAINS)} 중 실제로 사는 것을 적는다"
        )
    # 순차 의존 leaf 의 병렬(worker) 선언 차단 — worker 로 지정된 두 leaf 사이에
    # 의존 경로가 있으면 Dependencies 파생 동시 집합과 모순이다.
    workers = [sid for sid, m in rows.items() if m.group("mode").startswith("worker") and sid in leaf_ids]
    if len(workers) >= 2:
        edges = _leaf_dependency_edges(text)

        def reachable(src: str, dst: str) -> bool:
            seen: set[str] = set()
            stack = [src]
            while stack:
                node = stack.pop()
                if node == dst:
                    return True
                for dep in edges.get(node, []):
                    if dep not in seen:
                        seen.add(dep)
                        stack.append(dep)
            return False

        for i in range(len(workers)):
            for j in range(i + 1, len(workers)):
                a, b = workers[i], workers[j]
                if reachable(a, b) or reachable(b, a):
                    errors.append(
                        f"순차 의존 leaf 를 병렬 worker 로 선언했다: {a} ↔ {b} — "
                        "의존이 있는 쪽을 inline 으로 내리거나 배차 행을 지운다"
                    )
    return errors


# 계획 수치의 출처 (2026-07-21). 계기: 계획 전제 오류 5건이 전부 정본 대신
# 파생 지표(grep 수치·구버전 스키마·기억·잘린 화면)로 단정한 데서 났다.
# 규약 정본: the-source-repo/docs/measurement-provenance.md
# 적용 범위는 **DoD·통합 검증에 쓰인 수치**뿐이다 — 서술 속 배경 수치는 대상 아님.
# 발효일. 이날 이후 생성된 plan 만 검사한다 — 기존 문서는 기록으로 동결.
MEASUREMENT_RULE_SINCE = "2026-07-22"
DOD_LINE_RE = re.compile(r"^-\s*(?:\*\*)?(?:DoD|통합 검증)(?:\*\*)?\s*[:：](.+)$", re.M)
PROVENANCE_HEADING_RE = re.compile(r"^##[ 	]+수치 출처", re.M)
_DATEISH_RE = re.compile(r"\d{4}-\d{2}-\d{2}|v?\d+\.\d+")


def validate_measurement_provenance(text: str) -> list[str]:
    # 소급 적용하지 않는다 (문서 수명 규약 — 완료된 plan 은 기록으로 동결).
    # 규약 신설일 이전에 생성된 plan 은 검사 대상이 아니다.
    created = re.search(r"^>\s*생성:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if created is None or created.group(1) < MEASUREMENT_RULE_SINCE:
        return []
    errors: list[str] = []
    targets = []
    for m in DOD_LINE_RE.finditer(text):
        line = _DATEISH_RE.sub(" ", m.group(1))
        # 한국어 단위(건·개·줄)는 \w 라서 뒤쪽 lookahead 에 \w 를 쓰면 "75건" 을 놓친다.
        targets.extend(re.findall(r"(?<![\w.])\d{2,}(?![\d.])", line))
    if not targets:
        return errors
    if not PROVENANCE_HEADING_RE.search(text):
        errors.append(
            "DoD/통합 검증에 수치 " + ", ".join(sorted(set(targets))[:4])
            + " 가 있는데 '## 수치 출처' 절이 없다 — 그 수치를 낸 커맨드를 적는다 "
            "(the-source-repo/docs/measurement-provenance.md)"
        )
        return errors
    section = text.split("## 수치 출처", 1)[1]
    section = re.split(r"^## ", section, maxsplit=1, flags=re.M)[0]
    if "`" not in section:
        errors.append("'## 수치 출처' 절에 커맨드(백틱)가 없다 — 수치를 어떻게 냈는지 적는다")
    return errors


def validate(text: str) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_scaffold(text))
    errors.extend(validate_graph(text))
    errors.extend(validate_risk(text)[0])
    status = re.search(r"^Status:\s*(.+)$", text, re.M | re.I)
    status_value = status.group(1).strip() if status else ""
    # 실패 지점을 지목한다 (parse_dependency_value 와 같은 규율, 2026-08-01 tax-agent 마찰 #2):
    # 못 찾음(불릿·굵게로 쓴 Status 포함)과 값 미달을 한 메시지로 뭉개면
    # "approved 라고 적었는데 approved 아니라고 한다" 로 읽힌다.
    if not status:
        errors.append(
            "plan has no `Status:` line — 줄 맨 앞에서 시작해야 한다 (`- Status:` 불릿·굵게는 인식 안 됨)"
        )
    elif UNAPPROVED.search(status_value) or not APPROVED.search(status_value):
        errors.append(f"plan Status must explicitly contain approved or completed (현재 값: {status_value})")

    leaves = re.findall(r"^- \[(?: |x|X)\]\s+(.+)$", text, re.M)
    if len(leaves) < 2:
        errors.append("multi-step plan must contain at least two top-level checkbox leaves")
    for leaf in leaves:
        escaped = re.escape(leaf)
        block = re.search(rf"^- \[(?: |x|X)\]\s+{escaped}\s*$([\s\S]*?)(?=^- \[(?: |x|X)\]|^## |\Z)", text, re.M)
        if not block:
            continue
        body = block.group(1)
        for field, pattern in LEAF_FIELDS.items():
            match = pattern.search(body)
            if match is None:
                errors.append(f"step lacks required field {field}: {leaf}")
            elif not match.group(1).strip():
                errors.append(f"step field {field} is empty: {leaf}")

    for match in PLACEHOLDER.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"plan contains a placeholder marker at line {line}: {match.group(0)}")

    # IMP-041: 코드 펜스를 지운 사본에서 중괄호 템플릿 잔재 검사 (줄 번호 보존 위해 개행 유지 치환)
    fenceless = CODE_FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for match in BRACE_PLACEHOLDER.finditer(fenceless):
        line = fenceless.count("\n", 0, match.start()) + 1
        errors.append(f"plan contains a template brace placeholder at line {line}: {match.group(0)}")

    for match in FORBIDDEN_LEVEL_LABEL.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(
            f"plan uses an invented hierarchy label at line {line}: {match.group(0)} "
            "(용어 사전 — 레벨은 북극성/Milestone/Step, ID 는 M<순번>/step-N)"
        )

    errors.extend(validate_measurement_provenance(text))
    errors.extend(validate_dispatch(text))

    supersedes = SUPERSEDES.search(text)
    if supersedes is not None and not supersedes.group(1).strip():
        errors.append("Supersedes: declaration must name the plan doc it replaces")

    if not re.search(r"^##\s+(?:Scope Boundary|범위|중단점|run 전 scope)", text, re.M | re.I):
        errors.append("plan must declare scope boundary and stop conditions")
    if not EXECUTION_MODE.search(text):
        errors.append("plan must declare execution mode: continuous")
    if not STOP_POLICY.search(text):
        errors.append("plan must declare structured hard-stop conditions")
    rollback = ROLLBACK.search(text)
    if rollback is None or not rollback.group(1).strip():
        errors.append("plan must declare rollback/cleanup")
    decision = DECISION_HEADING.search(text)
    if not decision:
        errors.append("plan must contain ## 결정 로그 or ## Decision Log")
    else:
        tail = text[decision.end():]
        body = re.split(r"^##\s+", tail, maxsplit=1, flags=re.M)[0]
        if not DECISION_STATUS.search(body):
            errors.append("decision log must declare '- status: resolved' or '- status: none-required'")
        if UNRESOLVED.search(body):
            errors.append("decision log contains an unresolved decision")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    text = args.plan.read_text(encoding="utf-8", errors="replace")
    errors = validate(text)
    risk_tally = validate_risk(text)[1]
    result = {"status": "pass" if not errors else "fail", "plan": str(args.plan), "errors": errors}
    if risk_tally:
        result["risk"] = risk_tally
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"plan gate: {result['status'].upper()} ({args.plan})")
        if risk_tally:
            summary = " · ".join(f"{k} {v}" for k, v in sorted(risk_tally.items()))
            note = "  ← 미분류는 위험 쪽으로 취급한다" if risk_tally.get("미분류") else ""
            print(f"  risk: {summary}{note}")
        for error in errors:
            print(f"- {error}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
