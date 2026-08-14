#!/usr/bin/env bash
# handoff_commit.sh — 레포 수준 핸드오프(HANDOFF.md) 단독 커밋 + push (HO1 2026-07-27)
#
# 계약:
# - 어떤 실패도 세션 마감을 막지 않는다 — 문제는 [handoff] 경고로 알리고 항상 exit 0.
# - HANDOFF.md 만 커밋한다 — pathspec 커밋이라 다른 staged/dirty 변경은 절대 휩쓸리지 않는다.
# - linked worktree 에서는 쓰지 않는다(레포 수준 핸드오프는 main 체크아웃 소유).
#   워크트리 세션의 이어받기 정본은 plan doc 진행 로그다. 레포 수준으로 남길 말이
#   있을 때만 --to-main 으로 main 체크아웃에 대필하되, main 의 HANDOFF.md 가 dirty
#   면 보류한다(수기 변경 오염 방지).
#
# 사용:
#   handoff_commit.sh [--root <dir>]           # <dir>(기본 cwd) 레포의 HANDOFF.md 커밋+push
#   handoff_commit.sh --to-main [--root <dir>] # stdin 내용을 main 체크아웃 HANDOFF.md 로 대필
set -u

ROOT="."
TO_MAIN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --to-main) TO_MAIN=1; shift ;;
    *) echo "[handoff] 알 수 없는 인자: $1 (무시)"; shift ;;
  esac
done

warn_exit() { echo "[handoff] $1"; exit 0; }

git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1 \
  || warn_exit "git 레포가 아님 — 핸드오프 커밋 생략"
REPO_ROOT="$(git -C "$ROOT" rev-parse --show-toplevel)"

GIT_DIR_ABS="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-dir 2>/dev/null)"
COMMON_ABS="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
LINKED=0
[ -n "$GIT_DIR_ABS" ] && [ -n "$COMMON_ABS" ] && [ "$GIT_DIR_ABS" != "$COMMON_ABS" ] && LINKED=1

TARGET_ROOT="$REPO_ROOT"

if [ "$LINKED" = "1" ] && [ "$TO_MAIN" = "0" ]; then
  warn_exit "linked worktree — 레포 수준 핸드오프는 main 체크아웃 소유. 이 세션의 이어받기는 plan doc 진행 로그에 남기세요 (레포 수준 메모가 꼭 필요하면 --to-main)."
fi

if [ "$TO_MAIN" = "1" ]; then
  # main 체크아웃 = worktree list 첫 항목
  MAIN_ROOT="$(git -C "$REPO_ROOT" worktree list --porcelain | sed -n 's/^worktree //p' | head -1)"
  [ -n "$MAIN_ROOT" ] || warn_exit "main 체크아웃을 찾지 못함 — 보류"
  if [ -n "$(git -C "$MAIN_ROOT" status --porcelain -- HANDOFF.md 2>/dev/null)" ]; then
    warn_exit "main 체크아웃의 HANDOFF.md 에 미커밋 변경 있음 — 대필 보류 (수동 확인 필요: $MAIN_ROOT)"
  fi
  CONTENT="$(cat)"
  [ -n "$CONTENT" ] || warn_exit "--to-main 인데 stdin 이 비어 있음 — 보류"
  printf '%s\n' "$CONTENT" > "$MAIN_ROOT/HANDOFF.md"
  TARGET_ROOT="$MAIN_ROOT"
fi

[ -f "$TARGET_ROOT/HANDOFF.md" ] || warn_exit "HANDOFF.md 없음 ($TARGET_ROOT) — 커밋 생략"

if [ -z "$(git -C "$TARGET_ROOT" status --porcelain -- HANDOFF.md)" ]; then
  warn_exit "HANDOFF.md 변경 없음 — 커밋 생략"
fi

git -C "$TARGET_ROOT" add -- HANDOFF.md 2>/dev/null \
  || warn_exit "add 실패 — 커밋 생략"

# 기기 레이블: 한글 hostname 이 CP949 로 들어가 커밋 메시지가 깨진 실측(2026-07-27) —
# ASCII 만 남기고, 비면 OS 이름으로 대체한다(기기 구분은 uname 조합으로 충분).
HOST="$(hostname 2>/dev/null | LC_ALL=C tr -cd 'A-Za-z0-9._-')"
[ -n "$HOST" ] || HOST="$(uname -s 2>/dev/null | LC_ALL=C tr -cd 'A-Za-z0-9._-')"
[ -n "$HOST" ] || HOST=machine
STAMP="$(date +%Y-%m-%d) $HOST"
if ! git -C "$TARGET_ROOT" commit -m "chore(handoff): 세션 핸드오프 갱신 ($STAMP)" -- HANDOFF.md >/dev/null 2>&1; then
  warn_exit "커밋 실패(훅 거부 등) — 수동 확인 필요"
fi
echo "[handoff] 커밋 완료: HANDOFF.md 단독 ($(git -C "$TARGET_ROOT" rev-parse --short HEAD))"

if [ -z "$(git -C "$TARGET_ROOT" remote 2>/dev/null)" ]; then
  warn_exit "remote 없음 — 로컬 커밋만 (push 생략)"
fi
if git -C "$TARGET_ROOT" push >/dev/null 2>&1; then
  echo "[handoff] push 완료 — 다른 기기에서 pull 하면 이어받음"
else
  warn_exit "push 실패(오프라인·인증·upstream 미설정 가능) — 로컬 커밋은 완료, 나중에 push 필요"
fi
exit 0
