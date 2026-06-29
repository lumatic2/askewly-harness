#!/usr/bin/env bash
# 다른 git 레포에 AI-readiness 하네스를 부트스트랩.
#
# 사용:
#   bash /path/to/harness-bootstrap/scripts/init-ai-readiness.sh [<repo>] --full \
#        --mode <product|learning|tooling|workflow> [--kind <web|mobile|backend>]
#
# Windows PowerShell + WSL bash 사용자는 README의 bootstrap 예시를 참고.
#
# 갈래:
#   product   — 제품 만드는 레포. PRD + ARCH + 디자인 가이드 깔림.
#               kind=web 면 루트 DESIGN.md(Google Labs alpha 형식), mobile 면 docs/UI_GUIDE.md, backend 면 생략.
#   learning  — 공부·리서치 레포 (예: harness-engineering).
#               ROADMAP + BACKLOG + references/ + experiments/ + notes/.
#   tooling   — 스킬·스크립트·런타임 유지보수 레포.
#               ROADMAP + BACKLOG + changesets/ + 검증 checklist.
#   workflow  — 반복 업무 자동화 (세무·회계·운영).
#               DOMAIN + playbooks/ + data/(gitignored) + outputs/(gitignored) + config/sources.md.
#
# 공통: CLAUDE.md + AGENTS.md + ROADMAP.md + BACKLOG.md + docs/adr/.
# (pre-commit hallucinated-path hook 은 2026-06-20 제거 — changeset 20260620-drop-ai-readiness-precommit.
#  cartography scorer 가 gitignored references/ 클론 + 타repo 인용을 오탐해 게이트로 부적합.)
# CLAUDE.md 의 judge 강제 한 줄이 갈래마다 다름 (judge 위치 = 종 분류, v2.0).
#
# 레거시 플래그 (--prd / --arch / --ui) 는 --mode product 의 alias 로 호환 처리.
#
# 멱등(idempotent). 같은 레포에 다시 돌려도 안전.

set -e

REPO=""
FULL=0
PRD=0; ARCH=0; UI=0    # legacy
MODE=""
KIND=""
LEGACY_USED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --prd)  PRD=1;  LEGACY_USED=1; shift ;;
    --arch) ARCH=1; LEGACY_USED=1; shift ;;
    --ui)   UI=1;   LEGACY_USED=1; shift ;;
    --mode) MODE="$2"; shift 2 ;;
    --mode=*) MODE="${1#--mode=}"; shift ;;
    --kind) KIND="$2"; shift 2 ;;
    --kind=*) KIND="${1#--kind=}"; shift ;;
    -h|--help)
      sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) REPO="$1"; shift ;;
  esac
done
REPO="${REPO:-$(pwd)}"
REPO="$(cd "$REPO" && pwd)"

if [[ ! -d "$REPO/.git" ]]; then
  git -C "$REPO" init >/dev/null
  echo "[ok] git init (was not a repo)"
fi

# ── mode/kind 결정 ───────────────────────────────────────────────────────────
if [[ -z "$MODE" ]]; then
  if [[ $LEGACY_USED -eq 1 ]]; then
    MODE="product"
    echo "[warn] --prd/--arch/--ui 는 deprecated. --mode product 로 처리. 새 스킬은 --mode <갈래> 사용."
  else
    MODE="product"   # 기본
  fi
fi

case "$MODE" in
  product|learning|tooling|workflow) ;;
  *) echo "[error] unknown --mode: $MODE (product|learning|tooling|workflow)" >&2; exit 2 ;;
esac

if [[ "$MODE" == "product" ]]; then
  KIND="${KIND:-web}"
  case "$KIND" in
    web|mobile|backend) ;;
    *) echo "[error] unknown --kind: $KIND (web|mobile|backend)" >&2; exit 2 ;;
  esac
  # --full + product 면 PRD/ARCH/UI 자동 on (legacy 가 없을 때)
  if [[ $FULL -eq 1 && $LEGACY_USED -eq 0 ]]; then
    PRD=1; ARCH=1
    [[ "$KIND" != "backend" ]] && UI=1
  fi
elif [[ -n "$KIND" ]]; then
  echo "[warn] --kind 는 --mode product 한정. 무시됨."
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TPL="$SCRIPT_DIR/templates"

PROJECT_NAME="$(basename "$REPO")"

echo "[info] mode=$MODE${KIND:+ kind=$KIND} repo=$PROJECT_NAME"

write_harness_manifest() {
  local manifest_dir="$REPO/.harness"
  local manifest="$manifest_dir/manifest.json"
  mkdir -p "$manifest_dir"
  python3 - "$manifest" "$MODE" "${KIND:-}" "$PROJECT_NAME" "$REPO" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
mode = sys.argv[2]
kind = sys.argv[3]
project = sys.argv[4]
repo = Path(sys.argv[5])

if manifest.exists():
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
else:
    data = {}

def detect_existing_modes(repo: Path) -> list[str]:
    detected = []
    if (repo / "docs" / "PRD.md").exists() or (repo / "docs" / "ARCHITECTURE.md").exists():
        detected.append("product")
    if (repo / "references").exists() or (repo / "experiments").exists():
        detected.append("learning")
    if (repo / "changesets").exists():
        detected.append("tooling")
    if (repo / "docs" / "DOMAIN.md").exists() and (repo / "playbooks").exists():
        detected.append("workflow")
    return detected

existing_modes = detect_existing_modes(repo) if not manifest.exists() else []
primary = data.get("primary_mode") or (existing_modes[0] if existing_modes else mode)
modes = set(data.get("modes_enabled") or existing_modes)
modes.add(mode)
mode_kinds = dict(data.get("mode_kinds") or {})
if kind:
    mode_kinds[mode] = kind

data.update(
    {
        "schema_version": 1,
        "project": project,
        "primary_mode": primary,
        "modes_enabled": sorted(modes),
        "mode_kinds": mode_kinds,
        "last_bootstrap_mode": mode,
        "last_bootstrap_kind": kind or None,
        "updated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"),
        "notes": [
            "primary_mode is the original repo orientation unless intentionally changed.",
            "modes_enabled are additive capabilities; /harness chooses per run intent and ROADMAP target.",
        ],
    }
)
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[ok] .harness/manifest.json 갱신 (primary={primary}, modes={','.join(data['modes_enabled'])})")
PY
}

to_windows_path() {
  local p="$1"
  if command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$p" 2>/dev/null && return
  fi
  case "$p" in
    /mnt/[a-zA-Z]/*)
      local drive rest
      drive="${p#/mnt/}"
      drive="${drive%%/*}"
      rest="${p#"/mnt/$drive/"}"
      rest="${rest//\//\\}"
      printf '%s:\\%s\n' "$(printf '%s' "$drive" | tr '[:lower:]' '[:upper:]')" "$rest"
      return
      ;;
    /[a-zA-Z]/*)
      local drive rest
      drive="${p#/}"
      drive="${drive%%/*}"
      rest="${p#"/$drive/"}"
      rest="${rest//\//\\}"
      printf '%s:\\%s\n' "$(printf '%s' "$drive" | tr '[:lower:]' '[:upper:]')" "$rest"
      return
      ;;
  esac
  printf '%s\n' "$p"
}

# 중앙 evidence ledger 등록은 opt-in. HARNESS_EVIDENCE_REPO 를 evidence collector 가
# 있는 레포로 설정했을 때만 동작한다. 설정 안 하면 조용히 skip (대부분의 사용자).
locate_harness_evidence_repo() {
  if [[ -n "${HARNESS_EVIDENCE_REPO:-}" && -f "$HARNESS_EVIDENCE_REPO/scripts/collect_harness_evidence.py" ]]; then
    printf '%s\n' "$HARNESS_EVIDENCE_REPO"
    return
  fi
}

run_harness_evidence_collector() {
  local evidence_repo="$1"
  (
    cd "$evidence_repo" || exit 1
    if command -v py >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 py -3 scripts/collect_harness_evidence.py >/dev/null
    elif command -v python.exe >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 python.exe scripts/collect_harness_evidence.py >/dev/null
    elif command -v python >/dev/null 2>&1; then
      PYTHONIOENCODING=utf-8 python scripts/collect_harness_evidence.py >/dev/null
    else
      PYTHONIOENCODING=utf-8 python3 scripts/collect_harness_evidence.py >/dev/null
    fi
  )
}

register_harness_evidence_repo() {
  local evidence_repo config role repo_win repo_yaml
  evidence_repo="$(locate_harness_evidence_repo || true)"
  if [[ -z "$evidence_repo" ]]; then
    [[ -n "${HARNESS_EVIDENCE_REPO:-}" ]] && echo "[warn] HARNESS_EVIDENCE_REPO 에 collector 없음 — 등록 skip"
    return
  fi
  config="${HARNESS_EVIDENCE_CONFIG:-$evidence_repo/evidence/repos.local.yaml}"
  if [[ ! -f "$config" ]]; then
    echo "[warn] local evidence config 없음 — 등록 skip: $config"
    echo "       필요하면 evidence/repos.yaml 을 evidence/repos.local.yaml 로 복사해 로컬 경로를 넣어라."
    return
  fi

  repo_win="$(to_windows_path "$REPO")"
  repo_yaml="${repo_win//\\/\\\\}"
  role="$MODE"

  if grep -Fq "path: \"$repo_win\"" "$config" 2>/dev/null \
    || grep -Fq "path: \"$repo_yaml\"" "$config" 2>/dev/null \
    || grep -Fq "name: $PROJECT_NAME" "$config" 2>/dev/null; then
    echo "[skip] harness evidence repos.yaml 이미 등록됨 ($PROJECT_NAME)"
  else
    cat >> "$config" <<EOF
  - name: $PROJECT_NAME
    path: "$repo_yaml"
    role: $role
EOF
    echo "[ok] harness evidence repos.yaml 등록 ($PROJECT_NAME → $role)"
  fi

  if [[ -f "$evidence_repo/scripts/collect_harness_evidence.py" ]]; then
    run_harness_evidence_collector "$evidence_repo" \
      && echo "[ok] harness evidence ledger 갱신" \
      || echo "[warn] harness evidence ledger 갱신 실패 — bootstrap 자체는 완료"
  fi
}

create_agents_md() {
  local target="$REPO/AGENTS.md"
  if [[ -f "$target" ]]; then
    echo "[skip] AGENTS.md 이미 있음"
    return
  fi

  cat > "$target" <<EOF
# AGENTS.md — $PROJECT_NAME

> Codex 프로젝트 스코프 규칙. 생성: init-ai-readiness.sh

## 공통 원칙

공통 원칙은 홈 스코프 AGENTS.md 에서 이미 로드됐다고 가정한다. 여기서는 중복하지 않는다.

## 프로젝트 규칙

이 프로젝트의 상세 규칙·구조·관례는 같은 디렉토리의 \`CLAUDE.md\`에 있다.
세션 시작 시 반드시 \`./CLAUDE.md\` 와 \`./ROADMAP.md\`(있으면)를 읽고 시작할 것.

- \`CLAUDE.md\`: 프로젝트 기술 스택, 구조, 개발 명령어, 보호 파일 / 금지 사항, 기타 이 프로젝트 고유의 작업 방식
- \`ROADMAP.md\`: 현재 horizon·active milestone·다음 할 일. milestone 완료·compact 는 \`/harness\` 소유
- \`BACKLOG.md\`: 완료·보류·아카이브된 milestone 압축 이력. \`/harness\` 의 ROADMAP.md 150줄 budget 유지용
- \`session-end\`: ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 \`CLAUDE.local.md\` handoff 에만 반영

\`CLAUDE.md\`의 내용 중 Claude 전용 도구 호출 규칙은 Codex 환경에 맞게 해석하되, 프로젝트 구조·규칙은 그대로 따른다.
EOF
  echo "[ok] AGENTS.md skeleton 생성 (Codex stub)"
}

create_roadmap_md() {
  local target="$REPO/ROADMAP.md"
  if [[ -f "$target" ]]; then
    echo "[skip] ROADMAP.md 이미 있음"
    return
  fi

  case "$MODE" in
    product)
      cat > "$target" <<'EOF'
# ROADMAP

> 마지막 업데이트: YYYY-MM-DD
> 상태: product horizon
> 북극성: {CLAUDE.md 의 궁극 목표 한 줄}
> line budget: <=150

## Current Horizon

<!-- harness:goal id="product-horizon" -->
목표: {이번 horizon 의 제품/기술 목표 한 줄}

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 — {제목, 예: MVP 골격}
- DoD: {측정 가능한 완료 기준}
- Evidence: {테스트/빌드/문서/로그 경로}
- Gap: {왜 이 milestone 이 필요한가}
- Status: [ ]

<!-- harness:milestone id="M2" status="pending" priority="P1" -->
### M2 — {제목}
- DoD: {측정 가능한 완료 기준}
- Evidence: {테스트/빌드/문서/로그 경로}
- Gap: {왜 필요한가}
- Status: [ ]

## Next Candidates
- {아직 active 는 아닌 후보}

## Archive Pointer
완료 이력은 `BACKLOG.md` 참조. ROADMAP.md 는 150줄 이하 current horizon 만 유지한다. milestone 완료·compact 는 `/harness` 가 `roadmap_sync.py` 로 처리한다.

## 의사결정 이력
"왜 X 안 함?", "왜 Y를 미룸?" 같은 의도적 제외는 `docs/adr/` 에 ADR 로.
EOF
      ;;
    learning)
      cp "$TPL/learning/ROADMAP.md" "$target"
      ;;
    tooling)
      cp "$TPL/tooling/ROADMAP.md" "$target"
      ;;
    workflow)
      cat > "$target" <<'EOF'
# ROADMAP

> 마지막 업데이트: YYYY-MM-DD
> 상태: workflow horizon
> 북극성: {CLAUDE.md 의 궁극 목표 한 줄}
> line budget: <=150

## Current Horizon

<!-- harness:goal id="workflow-horizon" -->
목표: {이번 horizon 의 운영/자동화 목표 한 줄}

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 — {제목, 예: 핵심 도메인 기준 확정}
- DoD: {측정 가능한 완료 기준}
- Evidence: {DOMAIN/playbook/output/tool-call 경로}
- Gap: {왜 이 milestone 이 필요한가}
- Status: [ ]

<!-- harness:milestone id="M2" status="pending" priority="P1" -->
### M2 — {제목, 예: 첫 playbook 실전 적용}
- DoD: {측정 가능한 완료 기준}
- Evidence: {run.json/tool-calls/result 경로}
- Gap: {왜 필요한가}
- Status: [ ]

## Next Candidates
- {아직 active 는 아닌 후보}

## Archive Pointer
완료 이력은 `BACKLOG.md` 참조. ROADMAP.md 는 150줄 이하 current horizon 만 유지한다. milestone 완료·compact 는 `/harness` 가 `roadmap_sync.py` 로 처리한다.

## 의사결정 이력
"왜 X 기준을 씀?", "왜 Y 도구를 제외함?" 같은 의도적 선택은 `docs/adr/` 에 ADR 로.
EOF
      ;;
  esac
  echo "[ok] ROADMAP.md skeleton 생성 (mode=$MODE)"
}

create_backlog_md() {
  local target="$REPO/BACKLOG.md"
  if [[ -f "$target" ]]; then
    echo "[skip] BACKLOG.md 이미 있음"
    return
  fi

  cat > "$target" <<'EOF'
# BACKLOG

> 완료·보류·아카이브된 milestone 의 압축 이력. `ROADMAP.md` 는 current horizon 만 담고 150줄 이하로 유지한다.

## Completed

- (아직 없음)

## Deferred

- (아직 없음)

## Notes

- 완료 milestone 은 3~5줄로 압축한다: 완료일, 결과, evidence, 남은 gap.
- active/pending milestone 은 자동 아카이브하지 않는다.
- 이 파일과 ROADMAP.md 의 쓰기 소유자는 `/harness` 이다. `session-end` 는 ROADMAP 을 read-only 로 확인한다.
EOF
  echo "[ok] BACKLOG.md skeleton 생성"
}

# ── 1. (제거됨) pre-commit hallucinated-path hook ────────────────────────────
# pre-commit hallucinated-path hook 은 기본 설치하지 않는다 (gitignored 클론 +
# 타repo 인용을 오탐해 솔로 repo 커밋을 막는 false-gate 가 되기 쉬움).
write_harness_manifest

# ── 2. (--full) 공통 skeleton ────────────────────────────────────────────────
# judge 강제 한 줄 (mode 별 — v2.0 정의의 judge 위치 차이를 박제)
case "$MODE" in
  product)
    JUDGE_LINE='> 코드 변경 후 lint·테스트 통과 없이는 "완료" 보고 금지. 자동 도구가 통과하면 진실로 간주.'
    STRUCTURE_HINT="- 신규 기능 → 항상 계획 먼저, 구현 나중\n- 굵직한 결정은 \`docs/adr/\` 에 ADR 로 보존"
    ;;
  learning)
    JUDGE_LINE='> 새 reference 분석은 5섹션을 다 채우기 전에 정의 갱신·통찰 보고 금지. 인용은 출처 + 접근일 필수.'
    STRUCTURE_HINT="- 레포 분석은 \"전체 다 읽기\" X, \`references/ANALYSIS_TEMPLATE.md\` 의 5섹션 채우기 O\n- 시간 박스: 레포당 90분\n- 외부 정의 5개 이상 모이기 전 자기 정의 확정 금지"
    ;;
  tooling)
    JUDGE_LINE='> 스킬·런타임 변경은 targeted test/smoke/sync 증거 없이는 완료 보고 금지. 배포본까지 확인한다.'
    STRUCTURE_HINT="- 1 tooling changeset = 1 작업 단위\n- 변경 전 영향 파일과 배포 경로를 먼저 식별\n- SKILL.md 변경 시 \`bash setup.sh\` sync + trigger acceptance + hardening parity 확인"
    ;;
  workflow)
    JUDGE_LINE='> 외부 권위(법조문/기준/공식 도구) 인용 없는 수치·결론은 답변 금지. 모델 self-judgment 금지 (self-eval 천장).'
    STRUCTURE_HINT="- 모든 출력은 \`docs/DOMAIN.md\` 의 표 또는 공식 도구 호출 결과를 인용해야 함\n- playbook 의 \`근거\` 섹션 빈 채로 commit 금지\n- 기준일 변경 시 즉시 \`docs/DOMAIN.md\` 갱신"
    ;;
esac

if [[ $FULL -eq 1 ]]; then
  if [[ ! -f "$REPO/CLAUDE.md" ]]; then
    cat > "$REPO/CLAUDE.md" <<EOF
# $PROJECT_NAME

> 한 줄 설명. (갈래: $MODE${KIND:+ / $KIND})

## 기술 스택
-

## 프로젝트 구조
-

## 개발 명령어
\`\`\`bash
#
\`\`\`

## 작업 방식
$(printf '%b' "$STRUCTURE_HINT")

## ROADMAP 운영
- \`ROADMAP.md\` 는 current horizon / active milestone 장부이며 150줄 이하로 유지한다.
- \`BACKLOG.md\` 는 완료·보류·아카이브된 milestone 압축 이력이다.
- ROADMAP/BACKLOG 쓰기 소유자는 \`/harness\` 이다. milestone 완료·compact·horizon-check 는 \`roadmap_sync.py\` 로 처리한다.
- \`session-end\` 는 ROADMAP 을 수정하지 않는다. read-only 로 확인하고 \`CLAUDE.local.md\` handoff 에만 반영한다.

## ⚠ Judge 규약
$JUDGE_LINE

## 의사결정 이력
"왜 X 안 함?" 같은 *의도적으로 안 한 선택*은 \`docs/adr/\` 에 ADR 로 보존.
EOF
    echo "[ok] CLAUDE.md skeleton 생성 (mode=$MODE)"
  else
    # 기존 CLAUDE.md 위 retrofit: 통째 skip 하면 /harness §A 가 grep 하는 ## ⚠ Judge 규약 이 없어
    # judge 강제가 no-op 이 된다. 제목만 없으면 append (멱등).
    if grep -q "## ⚠ Judge 규약" "$REPO/CLAUDE.md"; then
      echo "[skip] CLAUDE.md 이미 있음 (Judge 규약 존재)"
    else
      printf '\n## ⚠ Judge 규약\n%s\n' "$JUDGE_LINE" >> "$REPO/CLAUDE.md"
      echo "[ok] CLAUDE.md 기존 — ## ⚠ Judge 규약 append (mode=$MODE)"
    fi
  fi

  if [[ ! -d "$REPO/docs/adr" ]]; then
    mkdir -p "$REPO/docs/adr"
    cat > "$REPO/docs/adr/README.md" <<'EOF'
# Architecture Decision Records

Michael Nygard ADR 포맷. 굵직한 의사결정·의도적 비활성·외부 제약을 보존.

각 ADR: Status / Context / Decision / Consequences. 한 번 쓰면 본문 수정 X
(supersede 만 허용). 자세한 가이드:
이 레포의 `docs/adr/README.md`

## 인덱스
- (아직 없음)
EOF
    echo "[ok] docs/adr/README.md skeleton 생성"
  else
    echo "[skip] docs/adr/ 이미 있음"
  fi

  create_agents_md
  create_roadmap_md
  create_backlog_md
fi

# ── 3. PRODUCT 분기 (PRD / ARCH / UI) ────────────────────────────────────────
if [[ "$MODE" == "product" && $PRD -eq 1 ]]; then
  mkdir -p "$REPO/docs"
  if [[ ! -f "$REPO/docs/PRD.md" ]]; then
    cat > "$REPO/docs/PRD.md" <<'EOF'
# PRD

## 목표
{이 프로젝트가 해결하려는 문제를 한 줄로}

## 사용자
{누가 쓰는지 — 페르소나 1-2명}

## 핵심 기능 (MVP)
1. {기능 1 — 한 문장}
2. {기능 2}
3. {기능 3}

## MVP 제외 사항
- {안 만들 것 1 — 왜 미루는지}
- {안 만들 것 2}

## 성공 지표
- {측정 가능한 기준 — 예: "주 3회 이상 사용", "온보딩 5분 이내"}
EOF
    echo "[ok] docs/PRD.md skeleton 생성"
  else
    echo "[skip] docs/PRD.md 이미 있음"
  fi
fi

if [[ "$MODE" == "product" && $ARCH -eq 1 ]]; then
  mkdir -p "$REPO/docs"
  if [[ ! -f "$REPO/docs/ARCHITECTURE.md" ]]; then
    cat > "$REPO/docs/ARCHITECTURE.md" <<'EOF'
# 아키텍처

## 디렉토리 구조
```
{루트 구조 — 핵심 폴더만, 자명한 것 제외}
```

## 패턴
{사용 디자인 패턴 — 예: Server Components 기본 / 인터랙션만 Client}

## 데이터 흐름
```
{입력 → 처리 → 저장 → 응답 의 한 줄}
```

## 외부 의존성
- {API · DB · 큐 — 각각 왜 선택했는지 ADR 링크}

## 상태 관리
{서버 상태 / 클라이언트 상태 분리 정책}
EOF
    echo "[ok] docs/ARCHITECTURE.md skeleton 생성"
  else
    echo "[skip] docs/ARCHITECTURE.md 이미 있음"
  fi
fi

if [[ "$MODE" == "product" && $UI -eq 1 ]]; then
  mkdir -p "$REPO/docs"
  if [[ "$KIND" == "mobile" ]]; then
    if [[ ! -f "$REPO/docs/UI_GUIDE.md" ]]; then
      cp "$TPL/product/UI_GUIDE_MOBILE.md" "$REPO/docs/UI_GUIDE.md"
      echo "[ok] docs/UI_GUIDE.md skeleton 생성 (mobile — RN/Flutter 톤)"
    else
      echo "[skip] docs/UI_GUIDE.md 이미 있음"
    fi
  else
    if [[ ! -f "$REPO/DESIGN.md" ]]; then
      cat > "$REPO/DESIGN.md" <<'EOF'
---
name: "Design System"
version: "alpha"
description: "{한 줄 톤 — 예: 도구처럼 보이는 대시보드, 마케팅 페이지 아님}"

colors:
  bg: "#0a0a0a"
  surface: "#141414"
  text: "#ffffff"
  textMuted: "#a3a3a3"
  accent: "#22c55e"
  danger: "#ef4444"

typography:
  heading: { fontFamily: "system-ui, sans-serif", fontWeight: 700 }
  body: { fontFamily: "system-ui, sans-serif", fontSize: "16px", lineHeight: "1.6" }

spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"

rounded:
  none: "0px"
  pill: "999px"
---

# Design System

> Google Labs DESIGN.md (alpha) 형식 — 도구(Claude Code·Cursor·Stitch)가 레포 루트에서 자동으로 읽는다.
> 본격 시스템(aesthetic family + lint + VRT)은 `/design-bootstrap` 으로 채운다.

## Overview
{이 제품의 시각 언어 한 문단. 예: "도구처럼 보여야 한다 — 매일 쓰는 대시보드, 마케팅 페이지가 아니라."}

## Colors
무채색 베이스 + accent 1톤. 보라/인디고 클리셰 금지.

## Typography
헤딩 {폰트·weight}. 본문 {폰트·size·line-height}.

## Layout
spacing scale 고정 — {예: 4·8·16·24·48}. container max·여백 규칙 여기.

## Shapes
border-radius {예: 0 / 999px 만 — 디폴트 8·12px 금지}.

## Components
{버튼·카드·인풋 규칙 — /design-bootstrap 이 채움}

## Do's and Don'ts
하지 마라 (AI 슬롭 안티패턴 — 팀의 디자인 매뉴얼이 있으면 거기에 맞춰 확장):
- `backdrop-filter: blur()` — glassmorphism = AI 템플릿의 가장 흔한 징후
- 배경 그라데이션 텍스트 — AI SaaS 랜딩 1번 특징
- "Powered by AI" 배지 — 장식, 가치 없음
- box-shadow 글로우 애니메이션 — 네온 글로우 = 슬롭
- 보라/인디고 브랜드 색 — "AI = 보라" 클리셰
- 모든 카드 동일 `rounded-2xl` — 균일 둥근 모서리 = 템플릿
- 배경 gradient orb (`blur-3xl`)
EOF
      echo "[ok] DESIGN.md (root) skeleton 생성 (web — Google Labs DESIGN.md alpha 형식)"
    else
      echo "[skip] DESIGN.md 이미 있음"
    fi
  fi
fi

# ── 4. LEARNING 분기 ─────────────────────────────────────────────────────────
if [[ "$MODE" == "learning" && $FULL -eq 1 ]]; then
  # references/
  mkdir -p "$REPO/references"
  if [[ ! -f "$REPO/references/README.md" ]]; then
    cat > "$REPO/references/README.md" <<'EOF'
# references/

분석한 외부 레포·자료의 인덱스. 클론은 이 폴더 안에만(루트에 stray repo 금지).

각 분석 노트는 `<handle>-<repo>/ANALYSIS.md` 5섹션 형식 — 템플릿: [ANALYSIS_TEMPLATE.md](ANALYSIS_TEMPLATE.md).

## 인덱스

| # | 레포 | 분석일 | 한 줄 요약 | 5섹션 완료 |
|---|------|--------|-----------|------------|
| 1 | {handle}/{repo} | YYYY-MM-DD | | ⬜ |

## 분석 원칙
- 시간 박스: 레포당 90분
- 5섹션 다 채우기 전엔 정의 갱신·통찰 보고 금지
- 인용은 출처 URL + 접근일 필수
EOF
    echo "[ok] references/README.md skeleton 생성"
  else
    echo "[skip] references/README.md 이미 있음"
  fi
  if [[ ! -f "$REPO/references/ANALYSIS_TEMPLATE.md" ]]; then
    cp "$TPL/learning/ANALYSIS_TEMPLATE.md" "$REPO/references/ANALYSIS_TEMPLATE.md"
    echo "[ok] references/ANALYSIS_TEMPLATE.md 생성"
  else
    echo "[skip] references/ANALYSIS_TEMPLATE.md 이미 있음"
  fi

  # experiments/
  mkdir -p "$REPO/experiments"
  if [[ ! -f "$REPO/experiments/README.md" ]]; then
    cat > "$REPO/experiments/README.md" <<'EOF'
# experiments/

손으로 직접 짜보는 작은 구현들. 각 실험은 `<NN>-<slug>/README.md` 4섹션 형식 —
템플릿: [EXPERIMENT_TEMPLATE.md](EXPERIMENT_TEMPLATE.md).

## 인덱스

| # | 슬러그 | 가설 (한 줄) | 결과 |
|---|--------|-------------|------|
| 01 | {slug} | | ⬜ |

## 실행 원칙
- mock 먼저, real 다음 (비용·시간 절약 + 가설 격리)
- `verify/` 폴더에 raw 출력 박제 (재현성)
- 통찰 섹션 비면 실험이 안 끝난 것
EOF
    echo "[ok] experiments/README.md skeleton 생성"
  else
    echo "[skip] experiments/README.md 이미 있음"
  fi
  if [[ ! -f "$REPO/experiments/EXPERIMENT_TEMPLATE.md" ]]; then
    cp "$TPL/learning/EXPERIMENT_TEMPLATE.md" "$REPO/experiments/EXPERIMENT_TEMPLATE.md"
    echo "[ok] experiments/EXPERIMENT_TEMPLATE.md 생성"
  else
    echo "[skip] experiments/EXPERIMENT_TEMPLATE.md 이미 있음"
  fi

  # notes/ (자유 형식)
  if [[ ! -d "$REPO/notes" ]]; then
    mkdir -p "$REPO/notes"
    touch "$REPO/notes/.gitkeep"
    echo "[ok] notes/ 생성 (자유 형식 리딩 메모)"
  else
    echo "[skip] notes/ 이미 있음"
  fi
fi

# ── 5. TOOLING 분기 ──────────────────────────────────────────────────────────
if [[ "$MODE" == "tooling" && $FULL -eq 1 ]]; then
  mkdir -p "$REPO/changesets"
  if [[ ! -f "$REPO/changesets/README.md" ]]; then
    cp "$TPL/tooling/CHANGESETS_README.md" "$REPO/changesets/README.md"
    echo "[ok] changesets/README.md skeleton 생성"
  else
    echo "[skip] changesets/README.md 이미 있음"
  fi
  if [[ ! -f "$REPO/changesets/CHANGESET_TEMPLATE.md" ]]; then
    cp "$TPL/tooling/CHANGESET_TEMPLATE.md" "$REPO/changesets/CHANGESET_TEMPLATE.md"
    echo "[ok] changesets/CHANGESET_TEMPLATE.md 생성"
  else
    echo "[skip] changesets/CHANGESET_TEMPLATE.md 이미 있음"
  fi
fi

# ── 6. WORKFLOW 분기 ─────────────────────────────────────────────────────────
if [[ "$MODE" == "workflow" && $FULL -eq 1 ]]; then
  mkdir -p "$REPO/docs"
  if [[ ! -f "$REPO/docs/DOMAIN.md" ]]; then
    cp "$TPL/workflow/DOMAIN.md" "$REPO/docs/DOMAIN.md"
    echo "[ok] docs/DOMAIN.md skeleton 생성"
  else
    echo "[skip] docs/DOMAIN.md 이미 있음"
  fi

  mkdir -p "$REPO/playbooks"
  if [[ ! -f "$REPO/playbooks/README.md" ]]; then
    cat > "$REPO/playbooks/README.md" <<'EOF'
# playbooks/

반복 업무 하나당 한 문서. 4섹션(입력 / 절차 / 체크리스트 / 근거) — 템플릿:
[PLAYBOOK_TEMPLATE.md](PLAYBOOK_TEMPLATE.md).

## 인덱스

| # | 슬러그 | 도메인 | 마지막 적용 | 적용 횟수 |
|---|--------|--------|------------|----------|
| 1 | {task-slug} | | YYYY-MM-DD | 0 |

## 실행 원칙
- 근거 섹션 빈 채로 commit 금지 (judge 강제)
- 기준일 확인 → `docs/DOMAIN.md` 표와 cross-check 후 실행
- 결과는 `outputs/{기수}/{task-slug}-{YYYYMMDD}.{ext}` 에 저장
EOF
    echo "[ok] playbooks/README.md skeleton 생성"
  else
    echo "[skip] playbooks/README.md 이미 있음"
  fi
  if [[ ! -f "$REPO/playbooks/PLAYBOOK_TEMPLATE.md" ]]; then
    cp "$TPL/workflow/PLAYBOOK_TEMPLATE.md" "$REPO/playbooks/PLAYBOOK_TEMPLATE.md"
    echo "[ok] playbooks/PLAYBOOK_TEMPLATE.md 생성"
  else
    echo "[skip] playbooks/PLAYBOOK_TEMPLATE.md 이미 있음"
  fi

  # data/ outputs/ — gitignored, gitkeep
  for d in data outputs; do
    if [[ ! -d "$REPO/$d" ]]; then
      mkdir -p "$REPO/$d"
      touch "$REPO/$d/.gitkeep"
      echo "[ok] $d/ 생성 (gitignored)"
    else
      echo "[skip] $d/ 이미 있음"
    fi
  done

  # .gitignore patch
  GITIGNORE="$REPO/.gitignore"
  touch "$GITIGNORE"
  for line in "data/" "outputs/"; do
    if ! grep -qxF "$line" "$GITIGNORE" 2>/dev/null; then
      printf '%s\n' "$line" >> "$GITIGNORE"
      echo "[ok] .gitignore += $line"
    fi
  done

  # config/sources.md
  mkdir -p "$REPO/config"
  if [[ ! -f "$REPO/config/sources.md" ]]; then
    cat > "$REPO/config/sources.md" <<'EOF'
# 외부 데이터 소스·도구 카탈로그

playbook 들이 호출하는 외부 권위(API·DB·계산기). 인증 정보는 여기 X — 환경변수 이름만.

## 공식 도구

| 이름 | 용도 | 호출 방법 | 인증 |
|------|------|----------|------|
| {예: KOSIS} | 통계 조회 | `kosis ...` | `KOSIS_API_KEY` |
| {예: DART} | 공시 조회 | API 엔드포인트 | `DART_API_KEY` |
| {예: law-mcp} | 법령 조회 | MCP 도구 | - |

## 인용 형식
- 결과 인용 시 위 표의 *이름 + 호출 인자 + 결과 한 줄* 박제
- 예: `kosis getStat KT_ZTITLE_2023 → 인구 51,558,034`

## ⚠ 주의
- 모든 외부 호출 결과에 호출 시점(타임스탬프) 기록
- 캐시된 결과를 *현재 사실* 로 다시 인용하지 말 것 (기준일 변경 가능성)
EOF
    echo "[ok] config/sources.md skeleton 생성"
  else
    echo "[skip] config/sources.md 이미 있음"
  fi
fi

# ── 6.5 PLANNING CASCADE 템플릿 (공통 — 모든 갈래) ────────────────────────────
# cascade plan docs(ADR 0007): Objective→Horizon→Milestone→Step. /harness §B0.5
# (planning authoring) 와 §B2-scope plan doc 이 이 템플릿들을 참조하므로 갈래 무관하게 깐다.
if [[ $FULL -eq 1 ]]; then
  mkdir -p "$REPO/templates"
  for tpl in OBJECTIVE_TEMPLATE HORIZON_TEMPLATE PLAN_TEMPLATE; do
    if [[ ! -f "$REPO/templates/$tpl.md" ]]; then
      cp "$TPL/$tpl.md" "$REPO/templates/$tpl.md"
      echo "[ok] templates/$tpl.md 생성"
    else
      echo "[skip] templates/$tpl.md 이미 있음"
    fi
  done
fi

# ── 7. (선택) harness evidence 대상 등록 ─────────────────────────────────────
echo ""
register_harness_evidence_repo

echo ""
case "$MODE" in
  product)
    echo "다음 단계 (product${KIND:+/$KIND}):"
    echo "  1. CLAUDE.md § 기술 스택 / 작업 방식 채우기"
    echo "  2. ROADMAP.md Current Horizon·M1~M2 DoD/Evidence 채우기 (150줄 이하)"
    echo "  3. docs/PRD.md 목표·핵심기능 채우기"
    [[ "$KIND" == "web" ]]    && echo "  4. DESIGN.md (root) colors/typography 토큰 + Do's and Don'ts 본 시스템 맞게 채우기 (본격: /design-bootstrap)"
    [[ "$KIND" == "mobile" ]] && echo "  4. docs/UI_GUIDE.md 색상 토큰 + 안티패턴 본 시스템 맞게 골라박기"
    echo "  5. 첫 ADR 작성: docs/adr/0001-{title}.md"
    echo "  운영: ROADMAP/BACKLOG 쓰기는 /harness 소유, session-end 는 read-only handoff"
    ;;
  learning)
    echo "다음 단계 (learning):"
    echo "  1. ROADMAP.md Current Horizon·M1~M3 DoD/Evidence 채우기 (150줄 이하)"
    echo "  2. 첫 reference 분석: references/<handle>-<repo>/ 클론 후 ANALYSIS_TEMPLATE 복사"
    echo "  3. 5섹션 다 채워야 정의 갱신·통찰 보고 가능 (judge 강제)"
    echo "  운영: ROADMAP/BACKLOG 쓰기는 /harness 소유, session-end 는 read-only handoff"
    ;;
  tooling)
    echo "다음 단계 (tooling):"
    echo "  1. ROADMAP.md Current Horizon·T1~T2 DoD/Evidence 채우기 (150줄 이하)"
    echo "  2. changesets/<YYYYMMDD>-<slug>/README.md 를 CHANGESET_TEMPLATE.md 로 생성"
    echo "  3. 영향 파일·배포 경로·검증 커맨드를 changeset 에 먼저 적기"
    echo "  4. SKILL.md 변경 시 setup.sh sync + trigger acceptance + hardening parity 확인"
    echo "  운영: ROADMAP/BACKLOG 쓰기는 /harness 소유, session-end 는 read-only handoff"
    ;;
  workflow)
    echo "다음 단계 (workflow):"
    echo "  1. ROADMAP.md Current Horizon·M1~M2 DoD/Evidence 채우기 (150줄 이하)"
    echo "  2. docs/DOMAIN.md 의 핵심 법규·기준일·정의 채우기"
    echo "  3. config/sources.md 의 외부 도구 카탈로그 채우기"
    echo "  4. 첫 playbook: playbooks/<task>.md (PLAYBOOK_TEMPLATE 복사) — 근거 섹션 필수"
    echo "  운영: ROADMAP/BACKLOG 쓰기는 /harness 소유, session-end 는 read-only handoff"
    ;;
esac
