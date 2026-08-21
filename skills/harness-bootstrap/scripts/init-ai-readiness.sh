#!/usr/bin/env bash
# 다른 git 레포에 AI-readiness 하네스를 부트스트랩.
#
# 사용:
#   bash /path/to/the-source-repo/scripts/init-ai-readiness.sh [<repo>] --full
#   bash ... <repo> --add <pack>        # 팩은 필요해질 때 하나씩
#
# Windows PowerShell + WSL bash 사용자는 README의 bootstrap 예시를 참고.
#
# **아무것도 묻지 않고 코어만 깐다** (2026-07-23, OI1). 코어 11개 —
#   CLAUDE.md · AGENTS.md · ROADMAP.md · docs/BACKLOG.md · docs/adr/README.md
#   changesets/{README,CHANGESET_TEMPLATE}.md · templates/PLAN_TEMPLATE.md
#   .harness/manifest.json
#
# 그 밖의 모든 것은 **lazy** — 필요해지는 시점에 `--add <pack>` 로:
#   product     docs/PRD.md · docs/ARCHITECTURE.md            (+ design 은 별도 팩)
#   design      DESIGN.md + lint hook (web) — design-pack 위임
#   ui-mobile   docs/UI_GUIDE.md
#   analysis    references/ + ANALYSIS_TEMPLATE
#   experiments experiments/                 notes  notes/
#   workflow    docs/DOMAIN.md · playbooks/ · config/sources.md · data/ · outputs/
#
# 왜 안 묻나: 폴더를 미리 깔지 않으므로 부팅 시점에 갈래를 정할 실체가 없다. 무엇이
# 필요한지는 `/harness-plan` spec readiness 가 그 문서를 실제로 요구하는 시점에 안다 — 부팅 때 추측하면
# 틀리고, 틀린 추측이 레포 정체성 문서에 박힌다. 구 `--mode` 4갈래는 2026-07-06 폐지됐는데
# 표기가 남아 폐지된 어휘를 신규 레포로 계속 출하했다(실측: 50개 중 15개 오염, OI1 step-1).
#
# 완료 판정 문구(CLAUDE.md 의 judge 한 줄)는 코어에 남지만 **중립 1종**이다 — 무엇으로
# 검증할지는 작업마다 `/harness-plan` 계획 분해(스캐폴딩 결정)의 `검증` 항목이 정한다. 레포 하나가 한 갈래일
# 것을 전제하지 않는다(이 레포만 해도 tooling·learning 양쪽이다).
#
# (pre-commit hallucinated-path hook 은 2026-06-20 제거 — changeset 20260620-drop-ai-readiness-precommit.
#  cartography scorer 가 gitignored references/ 클론 + 타repo 인용을 오탐해 게이트로 부적합.)
#
# 멱등(idempotent). 같은 레포에 다시 돌려도 안전.

set -e

REPO=""
FULL=0
ADD_PACKS=()

# 폐지된 인자는 **조용히 무시하지 않는다** — 낡은 호출자를 드러내려면 실패해야 한다.
retired_arg() {
  echo "[error] '$1' 은 폐지됐다 (2026-07-23, OI1)." >&2
  echo "        부팅은 갈래를 묻지 않고 코어만 깐다: bash init-ai-readiness.sh <repo> --full" >&2
  echo "        산출물별 파일은 필요할 때: --add <product|design|ui-mobile|analysis|experiments|notes|workflow|cascade>" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --add) ADD_PACKS+=("$2"); shift 2 ;;
    --add=*) ADD_PACKS+=("${1#--add=}"); shift ;;
    --mode|--mode=*|--kind|--kind=*|--prd|--arch|--ui) retired_arg "${1%%=*}" ;;
    -h|--help)
      sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
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

# ── 산출물 팩 (전부 lazy — 부팅은 코어만 깐다) ────────────────────────────────
VALID_PACKS="product design ui-mobile analysis experiments notes workflow cascade"
for pack in "${ADD_PACKS[@]:-}"; do
  [[ -z "$pack" ]] && continue
  case " $VALID_PACKS " in
    *" $pack "*) ;;
    *) echo "[error] unknown --add: $pack ($VALID_PACKS)" >&2; exit 2 ;;
  esac
done

has_pack() {
  local want="$1" p
  for p in "${ADD_PACKS[@]:-}"; do [[ "$p" == "$want" ]] && return 0; done
  return 1
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TPL="$SCRIPT_DIR/templates"
# 계획 템플릿(PLAN)의 정본은 레포 루트 `templates/` 하나다.
# 2026-07-22 (SS3 step-3) 이전에는 `scripts/templates/` 에도 같은 사본이 있었고,
# 그 사본이 갈라져 신규 레포가 받은 PLAN 템플릿이 plan 게이트를 통과 못 했다.
CASCADE_TPL="$SCRIPT_DIR/../templates"
SCORER="$HOME/.codex/skills/ai-readiness-cartography/scripts/score.py"
if [[ ! -f "$SCORER" ]]; then
  SCORER="$HOME/.claude/skills/ai-readiness-cartography/scripts/score.py"
fi
HAS_SCORER=1
if [[ ! -f "$SCORER" ]]; then
  HAS_SCORER=0
  echo "[warn] ai-readiness-cartography 스킬 미설치 — skeleton 생성은 계속, 스코어링은 skip"
  echo "       활성화하려면: /skill-toggle ai-readiness-cartography on"
fi

PROJECT_NAME="$(basename "$REPO")"

echo "[info] repo=$PROJECT_NAME${ADD_PACKS[*]:+ add=${ADD_PACKS[*]}}"

# --- 형제 레포 해석 (MM2 step-2, 2026-07-21) -------------------------------
# 정본 규칙은 `scripts/sibling_repo.py` 다. 셸에서는 파이썬을 import 할 수 없어
# 동등 규칙을 여기 옮긴다 — 순서가 갈리면 기기별로 다른 답이 나오므로, 바꿀 때는
# 두 곳을 함께 고친다(해석 순서: $HARNESS_SIBLING_ROOT → 이 스크립트의 레포 형제
# → ~/projects → %USERPROFILE%/projects).
sibling_roots() {
  local self_repo
  self_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" || self_repo=""
  local roots=()
  [[ -n "${HARNESS_SIBLING_ROOT:-}" ]] && roots+=("$HARNESS_SIBLING_ROOT")
  [[ -n "$self_repo" ]] && roots+=("$(dirname "$self_repo")")
  [[ -n "${HOME:-}" ]] && roots+=("$HOME/projects")
  [[ -n "${USERPROFILE:-}" ]] && roots+=("$USERPROFILE/projects")
  printf '%s
' "${roots[@]}"
}

# 의존물을 못 찾았을 때: 기본은 경고(부트스트랩 자체는 계속 — 그 기기에 없는 게
# 정상인 선택 기능이다). HARNESS_BOOTSTRAP_STRICT=1 이면 즉시 실패해 CI·검증에서
# 누락을 잡을 수 있다. 어느 쪽이든 **조용히 지나가지는 않는다**.
missing_dependency() {
  local what="$1" hint="$2"
  if [[ "${HARNESS_BOOTSTRAP_STRICT:-0}" == "1" ]]; then
    echo "[error] $what 을(를) 찾지 못했다 — $hint" >&2
    echo "        해석 순서: \$HARNESS_SIBLING_ROOT → 스크립트 레포의 형제 → ~/projects" >&2
    exit 1
  fi
  echo "[warn] $what 없음 — 관련 단계 skip ($hint)"
}

locate_design_pack() {
  # design-pack = 구 design-manual 툴링 (2026-07-17 custom-skills/harness-bootstrap/design-pack 이관)
  local candidates=(
    "${DESIGN_HARNESS_ROOT:-}"
    "${DESIGN_MANUAL_ROOT:-}"
    "$HOME/.claude/skills/harness-bootstrap/design-pack"
    "$HOME/.codex/skills/harness-bootstrap/design-pack"
  )
  local base
  while IFS= read -r base; do
    [[ -n "$base" ]] && candidates+=("$base/custom-skills/harness-bootstrap/design-pack")
  done < <(sibling_roots)
  local p
  for p in "${candidates[@]}"; do
    if [[ -n "$p" && -f "$p/scripts/init-design.sh" && -f "$p/scripts/lint/index.js" ]]; then
      printf '%s\n' "$p"
      return
    fi
  done
}

bootstrap_web_design_system() {
  local design_repo style stack init_script lint_script

  if compgen -G "$REPO/tokens/*.tokens.json" >/dev/null 2>&1; then
    echo "[skip] DESIGN.md bootstrap skipped (tokens/*.tokens.json is the design SSOT)"
    return 0
  fi

  if [[ -f "$REPO/DESIGN.md" ]]; then
    echo "[skip] DESIGN.md 이미 있음"
    return 0
  fi

  DESIGN_PACK_NOTE=""
  design_repo="$(locate_design_pack || true)"
  if [[ -z "$design_repo" ]]; then
    missing_dependency "design-pack" "expected ~/.claude/skills/harness-bootstrap/design-pack/scripts/init-design.sh"
    return 0
  fi

  DESIGN_PACK_NOTE=" (design-pack lint hook 설치됨)"
  export DESIGN_PACK_NOTE
  style="${HARNESS_DESIGN_STYLE:-minimal}"
  stack=""
  if [[ -f "$REPO/package.json" ]]; then
    if grep -q '"next"[[:space:]]*:' "$REPO/package.json"; then
      stack="nextjs"
    elif grep -q '"vite"[[:space:]]*:' "$REPO/package.json" && grep -q '"react"[[:space:]]*:' "$REPO/package.json"; then
      stack="vite-react"
    fi
  fi
  stack="${stack:-vanilla}"

  init_script="$design_repo/scripts/init-design.sh"
  lint_script="$design_repo/scripts/lint/index.js"
  echo "[info] web design system bootstrap via design-pack (style=$style, stack=$stack)"
  bash "$init_script" "$REPO" --style "$style" --stack "$stack"
  node "$lint_script" "$REPO/DESIGN.md"
}

write_harness_manifest() {
  local manifest_dir="$REPO/.harness"
  local manifest="$manifest_dir/manifest.json"
  mkdir -p "$manifest_dir"
  python3 - "$manifest" "$PROJECT_NAME" "${ADD_PACKS[*]:-}" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
project = sys.argv[2]
added = [p for p in sys.argv[3].split() if p]

if manifest.exists():
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
else:
    data = {}

# 2026-07-23 (OI1 step-2): `primary_mode`/`modes_enabled`/`mode_kinds` 를 **더 이상 쓰지 않는다**.
# 갈래 4분기는 2026-07-06 폐지됐고, 이 필드들이 그 어휘를 계속 재생산했다. 소비처는
# `collect_harness_evidence.infer_role()` 하나뿐인데 산출물 폴더 폴백이 이미 있어 무해하다.
# 기존 레포의 파일에 남아 있는 값은 지우지 않는다 — 남의 레포 파일을 일괄 수정하지 않는다.
packs = sorted(set(data.get("packs_added") or []) | set(added))
data.update(
    {
        "schema_version": 2,
        "project": project,
        "packs_added": packs,
        "updated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"),
        "notes": [
            "packs_added is a record of lazily installed artifact packs, not a repo classification.",
            "the harness flow (/harness-plan) decides what a run needs from ROADMAP target and the work itself, never from this file.",
        ],
    }
)
manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[ok] .harness/manifest.json 갱신{' (packs=' + ','.join(packs) + ')' if packs else ''}")
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

locate_harness_evidence_repo() {
  if [[ -n "${HARNESS_EVIDENCE_REPO:-}" && -f "$HARNESS_EVIDENCE_REPO/scripts/collect_harness_evidence.py" ]]; then
    printf '%s\n' "$HARNESS_EVIDENCE_REPO"
    return
  fi
  # 이 스크립트가 the-source-repo 안에 산다 — 자기 레포를 먼저 본다.
  local self_repo candidates=()
  self_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" || self_repo=""
  [[ -n "$self_repo" ]] && candidates+=("$self_repo")
  local base
  while IFS= read -r base; do
    [[ -n "$base" ]] && candidates+=("$base/the-source-repo")
  done < <(sibling_roots)
  for p in "${candidates[@]}"; do
    if [[ -f "$p/scripts/collect_harness_evidence.py" ]]; then
      printf '%s\n' "$p"
      return
    fi
  done
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
  # 임시 경로에 부팅한 레포는 등록하지 않는다 (2026-07-23, OI1 step-4).
  # 등록은 **영구**인데 검증용 레포는 곧 지워진다 — 그 비대칭이 실제로 쌓였다:
  # `repos.local.yaml` 에서 죽은 임시 레포 19건이 나왔고 6건은 이전 세션(MM8·SS3)의
  # 부트스트랩 테스트 잔해였다. 게이트를 검증할 때마다 설정이 더러워지면 검증을 피하게 된다.
  case "$REPO" in
    */scratchpad/*|*/Temp/*|*/tmp/*|/tmp/*)
      echo "[skip] harness evidence 등록 — 임시 경로 (검증용 레포는 영구 등록하지 않는다)"
      return ;;
  esac
  evidence_repo="$(locate_harness_evidence_repo || true)"
  if [[ -z "$evidence_repo" ]]; then
    missing_dependency "harness evidence collector" "expected <sibling>/the-source-repo/scripts/collect_harness_evidence.py"
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
  role="unknown"   # 갈래 분류 폐지(2026-07-23) — evidence collector 가 산출물 폴더로 판정한다

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

## 독립 운영 (Codex 소유)

이 프로젝트는 Claude 와 Codex 를 동등한 peer agent 로 운용한다. 어느 쪽도 영구 orchestrator 가 아니며, 현재 task 를 잡은 session owner 가 계획·수정·검증·커밋·handoff 를 소유한다.

**이 파일은 Codex 가 독립 소유한다** — \`CLAUDE.md\` 의 번역본·미러가 아니고, Codex 실사용 기준으로만 갱신하며 \`CLAUDE.md\` 와 내용을 맞출 의무가 없다(2026-08-22 미러링 폐지). 세션 시작 시 반드시 \`./CLAUDE.md\`(공유 프로젝트 컨텍스트), \`./ROADMAP.md\`(있으면), \`./HANDOFF.md\`(있으면 — git-tracked 핸드오프), \`./CLAUDE.local.md\`(있으면 — 기기-로컬 사실)를 읽고 시작한다.

- \`CLAUDE.md\`: 공유 프로젝트 컨텍스트 — 기술 스택, 구조, 개발 명령어, 보호 파일 / 금지 사항. 그 안의 Claude 전용 표면(slash·hook·subagent·MCP·memory)은 실행 지시가 아니다 — 같은 목적을 Codex 실재 수단으로 수행하고, 불가하면 보고한다
- \`ROADMAP.md\`: active milestone·다음 할 일. milestone 완료·compact 는 \`/harness-done\` 소유
- \`docs/BACKLOG.md\`: 완료·보류·아카이브된 milestone 압축 이력. \`/harness-done\` 의 ROADMAP.md 150줄 budget 유지용
- \`session-end\`: ROADMAP 을 수정하지 않고 read-only 로 확인한 뒤 \`HANDOFF.md\` handoff(git-tracked, 단독 커밋+push)에만 반영
- **완료 계약**: 작업 단위 산출물 기본 = changeset — milestone 당 README 1개(step 은 절, 기록-합본) + 인덱스 행. **1 step = 1 commit** — 커밋까지가 완료
- 두 런타임이 공유하는 규칙은 공유 문서(\`docs/\`·ADR·changeset·스킬 소스)로 승격한다 — 이 파일과 \`CLAUDE.md\` 에 같은 규칙을 복제하지 않는다

## Context landmarks

이 파일은 root landmark다. repo가 커져 root 설명만으로 부족해지면 하위 디렉터리에도 scoped \`AGENTS.md\`를 둔다.

추가 후보 기준:
- 하위 디렉터리가 별도 stack/config/test/deploy 규칙을 가진다.
- 파일 수·깊이·symbol/reference 중심성이 높아 수정 전 반드시 읽어야 한다.
- agent가 반복해서 잘못된 파일을 고르거나 local convention을 놓친다.

## Role lanes

큰 작업의 planning/review에서는 역할을 이름 붙여 분리한다.

- explorer: 관련 파일·규칙·선례를 찾는다.
- planner: 결정·의존성·작업 순서를 검토한다.
- reviewer: diff 품질·scope drift·maintainability를 반박한다.
- qa: 실행 증거·failure mode·smoke를 확인한다.
- gate: 완료 주장과 evidence를 최종 대조한다.

role lane은 자동 subagent/team 실행을 뜻하지 않는다. 도구가 가능하고 위험도가 맞을 때만 위임하고, 기본은 같은 세션에서 lane별로 분리 검토한다.
EOF
  echo "[ok] AGENTS.md skeleton 생성 (Codex 소유 — 독립 운영)"
}

create_roadmap_md() {
  local target="$REPO/ROADMAP.md"
  if [[ -f "$target" ]]; then
    echo "[skip] ROADMAP.md 이미 있음"
    return
  fi

  cat > "$target" <<'EOF'
# ROADMAP

> 마지막 업데이트: YYYY-MM-DD
> 상태: {이 레포가 지금 무엇을 하고 있나 한 줄}
> 북극성: {`CLAUDE.md` 맨 위 「북극성」 절의 한 줄 — 비어 있으면 그것부터 사용자와 세운다}
> line budget: <=150

## 북극성 요약

<!-- harness:goal id="north-star" -->
목표: {CLAUDE.md 「북극성」 절의 한 줄 요약 — 방향이 바뀔 때만 갱신}

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 — {제목}
- DoD: {측정 가능한 완료 기준 — 무엇을 돌려 무엇을 확인하면 끝인가}
- Evidence: {그 확인이 남는 자리 — 테스트·로그·문서 경로}
- Gap: {왜 이 milestone 이 필요한가}
- Status: [ ]

<!-- harness:milestone id="M2" status="pending" priority="P1" -->
### M2 — {제목}
- DoD: {측정 가능한 완료 기준}
- Evidence: {경로}
- Gap: {왜 필요한가}
- Status: [ ]

## Next Candidates
- {아직 active 는 아닌 후보}

## Archive Pointer
완료 이력은 `docs/BACKLOG.md` 참조. ROADMAP.md 는 150줄 이하 상태판만 유지한다. milestone 완료·compact 는 `/harness-done` 이 처리한다.

## 의사결정 이력
"왜 X 안 함?", "왜 Y를 미룸?" 같은 의도적 제외는 `docs/adr/` 에 ADR 로.
EOF
  echo "[ok] ROADMAP.md skeleton 생성"
}

create_backlog_md() {
  # UD3 step-1: BACKLOG.md scaffolds into docs/ (deeper — archive, not
  # discoverability-critical). New repos use this path;
  # pre-relocation repos may still carry a root BACKLOG.md (step-2 fleet migration).
  local target="$REPO/docs/BACKLOG.md"
  mkdir -p "$REPO/docs"
  if [[ -f "$target" || -f "$REPO/BACKLOG.md" ]]; then
    echo "[skip] BACKLOG.md 이미 있음"
    return
  fi

  cat > "$target" <<'EOF'
# BACKLOG

> 완료·보류·아카이브된 milestone 의 압축 이력. `ROADMAP.md` 는 현재 상태판만 담고 150줄 이하로 유지한다.

## Completed

- (아직 없음)

## Deferred

- (아직 없음)

## Notes

- 완료 milestone 은 3~5줄로 압축한다: 완료일, 결과, evidence, 남은 gap.
- active/pending milestone 은 자동 아카이브하지 않는다.
- 이 파일과 ROADMAP.md 의 쓰기 소유자는 하네스 흐름(`/harness-done`)이다. `session-end` 는 ROADMAP 을 read-only 로 확인한다.
EOF
  echo "[ok] docs/BACKLOG.md skeleton 생성"
}

# ── 1. (제거됨) pre-commit hallucinated-path hook ────────────────────────────
# 2026-06-20: 자동 hook 설치 제거. cartography scorer 가 gitignored references/
# 클론 + 타repo 인용을 hallucinated 로 오탐해 솔로 repo 커밋을 막는 false-gate 였다.
# 경로 정합성 점검이 필요하면 on-demand 로 /ai-readiness-cartography 를 호출한다.
write_harness_manifest

# ── 2. (--full) 공통 skeleton ────────────────────────────────────────────────
# 완료 판정 한 줄 — **중립 1종** (2026-07-23 OI1 step-2).
# 구 방식은 갈래마다 다른 문구를 심었고, 그게 두 가지를 고장냈다: ① 레포 하나가 한 갈래일
# 것을 전제했다(이 레포만 해도 tooling·learning 양쪽이다) ② 폐지된 규약이 화석으로 남아
# 계속 출하됐다 — learning 문구는 이 레포가 2026-07-17 에 폐지한 "90분 시간박스·5섹션 완주"를
# 신규 레포에 심고 있었다. 무엇으로 검증할지는 부팅 시점이 아니라 작업 시점에 정한다.
JUDGE_LINE='> 검증 증거(테스트·스모크·실제 구동·출처) 없이 "완료" 보고 금지. 무엇으로 검증하는지는 그 작업의 `/harness-plan` 계획 분해 스캐폴딩 결정 `검증` 항목이 정한다.'
STRUCTURE_HINT="- 무엇을 만들든 계획 먼저, 구현 나중
- 굵직한 결정은 \`docs/adr/\` 에 ADR 로 보존
- 이 절은 이 레포에서 실제로 반복되는 규칙으로 채운다(비어 있으면 지운다)"

if [[ $FULL -eq 1 ]]; then
  if [[ ! -f "$REPO/CLAUDE.md" ]]; then
    # 북극성 절 양식 (고정 — 2026-07-24 사용자 확정. 여기 찍는 것이 형식 정본):
#   제목 = 「## 북극성」으로 시작(꼬리말 자유), CLAUDE.md 첫 ## 절.
#   파서 = Stop 훅 plan_position_stop — 인용구(>)·하위 제목(#)을 건너뛰고
#   첫 일반 문단의 첫 문장을 매 턴 사용자에게 표시한다.
#   → 북극성 본문은 인용구·하위 제목 밖의 첫 문단에, 한 문장으로 시작해야 한다.
cat > "$REPO/CLAUDE.md" <<EOF
# $PROJECT_NAME

> 한 줄 설명.

## 북극성 — 사용자 소유, 승인 없이 수정 금지

> 이 절은 **사용자 소유**다. 에이전트는 문구 후보를 제안하고, 대화에서 확정 문구를 되읽어 **명시 승인을 받은 뒤에만** 그대로 기록한다. 승인 전 자율 수정 금지. 갱신은 **방향 자체가 바뀔 때만** — Milestone 완료는 여기를 바꾸지 않는다.

{이 프로젝트가 무엇을 이루려 하는가 — 한 문장. 아직 없으면 사용자와 정하기 전까지 비워 둔다.}

**성공 모습 (이게 되면 끝)**
- {관측 가능한 상태로 2~4줄}

**움직이는 축 (무엇을 끌어올리나)**
- {지금 → 어디로, 무엇으로 재나}

## 기술 스택
<!-- TODO: 채우기 전엔 빈 섹션임을 알 수 있게 표시만 두고 지우지 않는다 -->

## 프로젝트 구조
<!-- TODO: 채우기 전엔 빈 섹션임을 알 수 있게 표시만 두고 지우지 않는다 -->

## 개발 명령어
\`\`\`bash
# TODO: dev/test/build/lint 명령어를 채운다
\`\`\`

## Gotchas
<!-- TODO: 비명백한 동작·필수 env var·알려진 함정을 채운다. 없다는 확신이 서면 이 섹션 자체를 지워도 된다. -->

## 작업 방식
$(printf '%b' "$STRUCTURE_HINT")

## ROADMAP 운영
- \`ROADMAP.md\` 는 active milestone 상태판이며 150줄 이하로 유지한다.
- \`docs/BACKLOG.md\` 는 완료·보류·아카이브된 milestone 압축 이력이다.
- ROADMAP/BACKLOG 쓰기 소유자는 하네스 흐름이다. milestone 완료·compact 는 \`/harness-done\` 이 처리한다.
- \`session-end\` 는 ROADMAP 을 수정하지 않는다. read-only 로 확인하고 \`HANDOFF.md\` handoff(git-tracked)에만 반영한다.

## 컨텍스트 갱신 규칙
- 사용자가 같은 교정을 2회 이상 반복하거나 "항상 ~해줘"·"다시는 ~하지 마" 식으로 말하면, 메모리에 넣지 말고 그 자리에서 이 파일에 추가를 제안한다(두 런타임 공통이면 공유 문서·스킬 소스 승격을 제안).
- 이 레포에만 해당하는 사실은 여기에, 모든 레포에 해당하면 자기 런타임 글로벌(Claude→\`~/.claude/CLAUDE.md\`, Codex→\`~/.codex/AGENTS.md\`)에 제안한다 — 헷갈리면 물어본다.
- 이 \`CLAUDE.md\` 는 Claude 소유, \`AGENTS.md\` 는 Codex 소유다(미러링 폐지, 2026-08-22). 둘 다 지켜야 할 규칙은 양쪽에 복제하지 말고 공유 문서(\`docs/\`·ADR·스킬 소스)로 승격하고 각 파일엔 포인터만 둔다.
- 정기적으로(주 1회 또는 감이 안 잡힐 때) \`context-manager\` 를 "전체 점검"으로 돌려 배치 오류·drift 를 확인한다.

## ⚠ Judge 규약
$JUDGE_LINE

## 의사결정 이력
"왜 X 안 함?" 같은 *의도적으로 안 한 선택*은 \`docs/adr/\` 에 ADR 로 보존.
EOF
    echo "[ok] CLAUDE.md skeleton 생성"
  else
    # 기존 CLAUDE.md 위 retrofit: 통째 skip 하면 하네스 탐색(/harness-plan)이 grep 하는 ## ⚠ Judge 규약 이 없어
    # judge 강제가 no-op 이 된다. 제목만 없으면 append (멱등).
    if grep -q "## ⚠ Judge 규약" "$REPO/CLAUDE.md"; then
      echo "[skip] CLAUDE.md 이미 있음 (Judge 규약 존재)"
    else
      printf '\n## ⚠ Judge 규약\n%s\n' "$JUDGE_LINE" >> "$REPO/CLAUDE.md"
      echo "[ok] CLAUDE.md 기존 — ## ⚠ Judge 규약 append"
    fi

    if grep -q "## 컨텍스트 갱신 규칙" "$REPO/CLAUDE.md"; then
      echo "[skip] CLAUDE.md 컨텍스트 갱신 규칙 이미 있음"
    else
      cat >> "$REPO/CLAUDE.md" <<'CTXEOF'

## 컨텍스트 갱신 규칙
- 사용자가 같은 교정을 2회 이상 반복하거나 "항상 ~해줘"·"다시는 ~하지 마" 식으로 말하면, 메모리에 넣지 말고 그 자리에서 이 파일에 추가를 제안한다(두 런타임 공통이면 공유 문서·스킬 소스 승격을 제안).
- 이 레포에만 해당하는 사실은 여기에, 모든 레포에 해당하면 자기 런타임 글로벌(Claude→`~/.claude/CLAUDE.md`, Codex→`~/.codex/AGENTS.md`)에 제안한다 — 헷갈리면 물어본다.
- 이 `CLAUDE.md` 는 Claude 소유, `AGENTS.md` 는 Codex 소유다(미러링 폐지, 2026-08-22). 둘 다 지켜야 할 규칙은 양쪽에 복제하지 말고 공유 문서(`docs/`·ADR·스킬 소스)로 승격하고 각 파일엔 포인터만 둔다.
- 정기적으로(주 1회 또는 감이 안 잡힐 때) `context-manager` 를 "전체 점검"으로 돌려 배치 오류·drift 를 확인한다.
CTXEOF
      echo "[ok] CLAUDE.md 기존 — ## 컨텍스트 갱신 규칙 append"
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
if has_pack product; then
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

if has_pack product; then
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

if has_pack ui-mobile || has_pack design; then
  mkdir -p "$REPO/docs"
  if has_pack ui-mobile; then
    if [[ ! -f "$REPO/docs/UI_GUIDE.md" ]]; then
      cp "$TPL/product/UI_GUIDE_MOBILE.md" "$REPO/docs/UI_GUIDE.md"
      echo "[ok] docs/UI_GUIDE.md skeleton 생성 (mobile — RN/Flutter 톤)"
    else
      echo "[skip] docs/UI_GUIDE.md 이미 있음"
    fi
  else
    bootstrap_web_design_system
  fi
fi

# ── 4. LEARNING 분기 ─────────────────────────────────────────────────────────
if has_pack analysis; then
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

  # experiments/·notes/ 는 선행 생성하지 않는다 (CS4 2026-07-17 — fleet 실측 빈 폴더 5개).
  # 첫 사용 시: bash init-ai-readiness.sh <repo> --add experiments|notes
  echo "[info] experiments/·notes/ 는 lazy — 첫 실험/메모 때 '--add experiments|notes' 로 생성"
fi

# ── 4b. LAZY 팩 추가 (--add, CS4 2026-07-17) ─────────────────────────────────
add_pack_experiments() {
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
  if [[ ! -f "$REPO/experiments/EXPERIMENT_TEMPLATE.md" && -f "$TPL/learning/EXPERIMENT_TEMPLATE.md" ]]; then
    cp "$TPL/learning/EXPERIMENT_TEMPLATE.md" "$REPO/experiments/EXPERIMENT_TEMPLATE.md"
    echo "[ok] experiments/EXPERIMENT_TEMPLATE.md 생성"
  fi
}

add_pack_notes() {
  if [[ ! -d "$REPO/notes" ]]; then
    mkdir -p "$REPO/notes"
    touch "$REPO/notes/.gitkeep"
    echo "[ok] notes/ 생성 (자유 형식 리딩 메모)"
  else
    echo "[skip] notes/ 이미 있음"
  fi
}

has_pack experiments && add_pack_experiments
has_pack notes && add_pack_notes

# ── 5. CHANGESETS (전 모드 공통 — HU2 2026-07-06: changeset = 범용 step 기록) ──
if [[ $FULL -eq 1 ]]; then
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
if has_pack workflow; then
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
# 계획 템플릿 (2계층, 2026-07-23 C4): 북극성(CLAUDE.md 절) → 작업 단위 계획서.
# /harness-plan 의 계획 작성·계획 분해가 이 템플릿들을 참조하므로 갈래 무관하게 깐다.
# lazy 부트스트랩 레포는 `--add cascade` 로 받는다 (2026-08-01 tax-agent 마찰 —
# --full 전용이라 plan gate 가 요구하는 형식의 정본을 받을 길이 없었다).
if [[ $FULL -eq 1 ]] || has_pack cascade; then
  mkdir -p "$REPO/templates"
  # OBJECTIVE_TEMPLATE 은 2026-07-23 재조립 C4 로 은퇴 — 북극성은 CLAUDE.md 절이다.
  # REPORT_TEMPLATE 은 /harness-done 완료 보고서 3섹션 정본 — 같은 전달 경로 (2026-08-01).
  for tpl in PLAN_TEMPLATE REPORT_TEMPLATE; do
    if [[ ! -f "$REPO/templates/$tpl.md" ]]; then
      cp "$CASCADE_TPL/$tpl.md" "$REPO/templates/$tpl.md"
      echo "[ok] templates/$tpl.md 생성"
    else
      echo "[skip] templates/$tpl.md 이미 있음"
    fi
  done
fi

# ── 7. 스코어 출력 ───────────────────────────────────────────────────────────
if [[ $HAS_SCORER -eq 1 ]]; then
  TMP_JSON="$(python3 -c "import tempfile; print(tempfile.NamedTemporaryFile(suffix='.json', delete=False).name)")"
  trap 'rm -f "$TMP_JSON"' EXIT

  echo ""
  echo "=== AI-Readiness Score ($PROJECT_NAME) ==="
  PYTHONIOENCODING=utf-8 python3 "$SCORER" "$REPO" --json "$TMP_JSON" 2>&1 \
    | grep -E "^\*\*Score|^\*\*Grade|^\*\*Modules|^\| [A-G] |^- |^\| [0-9] " \
    | head -40
else
  echo ""
  echo "[info] 스코어링 skip — ai-readiness-cartography 스킬 활성화 후 재실행"
fi

# ── 8. harness evidence 대상 등록 ────────────────────────────────────────────
echo ""
register_harness_evidence_repo

echo ""
# MM8 step-1 (2026-07-21): lazy 부트스트랩(--full 없음)은 `.harness/manifest.json` 만
# 만드는데, 아래 "다음 단계" 는 ROADMAP.md·CHANGESET_TEMPLATE.md 처럼 **설치되지 않은
# 파일**을 가리켰다. 안내가 없는 것을 가리키면 그건 안내가 아니라 오정보다.
# 실제 설치물을 먼저 대조해, 빠진 게 있으면 무엇을 어떻게 받는지 한 줄로 알린다.
missing_scaffold=()
[[ -f "$REPO/ROADMAP.md" ]] || missing_scaffold+=("ROADMAP.md")
[[ -f "$REPO/CLAUDE.md" ]] || missing_scaffold+=("CLAUDE.md")
[[ ! -f "$REPO/changesets/CHANGESET_TEMPLATE.md" ]] && missing_scaffold+=("changesets/CHANGESET_TEMPLATE.md")
if (( ${#missing_scaffold[@]} > 0 )); then
  echo "[warn] 아직 설치되지 않은 스캐폴딩: ${missing_scaffold[*]}"
  echo "       아래 안내 중 이 파일들을 가리키는 항목은 먼저 설치해야 한다 —"
  echo "       전체: 같은 커맨드에 --full · 부분: --add <pack>"
  echo ""
fi
echo "다음 단계:"
echo "  1. CLAUDE.md § 기술 스택 / 프로젝트 구조 / 작업 방식 채우기"
echo "  2. CLAUDE.md 맨 위 「북극성」 절 채우기 (문구는 사용자 소유 — 승인 후에만 기록)"
echo "  3. ROADMAP.md M1~M2 DoD/Evidence 채우기 (150줄 이하)"
echo "  4. 첫 작업은 /harness-plan 으로 — 필요한 문서(PRD·DOMAIN·references 등)는 그때 깔린다"
echo "  운영: ROADMAP/BACKLOG 쓰기는 하네스 흐름(/harness-done) 소유, session-end 는 read-only handoff"
echo ""
echo "  산출물 팩은 필요해질 때만: --add <product|design|ui-mobile|analysis|experiments|notes|workflow|cascade>"
