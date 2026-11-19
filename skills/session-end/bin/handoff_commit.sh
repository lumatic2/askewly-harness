#!/usr/bin/env bash
# handoff_commit.sh — 레포 수준 핸드오프(HANDOFF.md) 단독 커밋 + push (HO1 2026-07-27)
#
# 계약:
# - 어떤 실패도 세션 마감을 막지 않는다 — 문제는 [handoff] 경고로 알리고 항상 exit 0.
# - HANDOFF.md 만 커밋한다 — pathspec 커밋이라 다른 staged/dirty 변경은 절대 휩쓸리지 않는다.
# - linked worktree 에서는 main 체크아웃의 HANDOFF.md 를 커밋한다 — handoff_merge.py 가 항목 단위로
#   병합하므로(v3 · 2026-11-07 M25) main 을 덮을 위험이 없다. 구 「워크트리는 거부」 규칙은 폐지.
# - 병합기가 백로그를 바꿨으면 `<git-dir>/HANDOFF_WITH` 에 그 경로를 남긴다 — 같은 커밋에 자동으로 넣고 지운다
#   (14일 내림은 어느 마감에서나 일어나므로 --with 를 기억하는 데 기대지 않는다).
# - --no-push: 로컬 커밋만 (session-end --checkpoint 용).
# - push 는 이 세션 것으로 보이는 커밋만 앞서 있을 때 한다 (2026-11-07). `git push` 는 브랜치 전체를
#   올리므로, 다른 세션이 아직 리뷰 중인 로컬 커밋까지 함께 올라갔다(2026-11-05 실측 2bbdc82).
#   앞선 커밋이 전부 chore(handoff)·chore(hygiene) 면 push, 그 밖이 섞이면 목록을 찍고 보류한다.
#   그 커밋이 이 세션 것임을 확인했으면 --push-all 로 다시 돌린다(HANDOFF 변경이 없어도 push 단계로 간다).
# - 완료 근거: <git-dir>/HANDOFF_COMMIT_MSG (handoff_merge.py 가 덧붙인다)가 있으면 커밋 본문에 붙이고,
#   커밋 성공 시 지운다. 커밋이 거부되면 출력 끝 40줄을 stderr 로 보이고 파일은 남긴다(다음 시도에 쓰인다).
# - --to-main 은 은퇴했다(2026-11-07 M25) — 알 수 없는 인자 경고만 낸다.
#
# 사용:
#   handoff_commit.sh [--root <dir>] [--no-push|--push-all] [--with <path>]...  # HANDOFF.md 커밋+push
#     --with: 같은 커밋에 넣을 경로(레포 루트 기준) — handoff_merge.py 가 날짜 없는 기다리는 일을
#             docs/BACKLOG.md 로 보냈을 때 그 파일 (2026-11-07). 반복 가능.
set -u

ROOT="."
NO_PUSH=0
PUSH_ALL=0
WITH=()
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --no-push) NO_PUSH=1; shift ;;
    --push-all) PUSH_ALL=1; shift ;;
    --with) WITH+=("$2"); shift 2 ;;
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

if [ "$LINKED" = "1" ]; then
  # 워크트리 세션: handoff_merge.py 가 main 체크아웃의 HANDOFF.md 에 병합했다 — 그걸 커밋한다.
  MAIN_ROOT="$(git -C "$REPO_ROOT" worktree list --porcelain | sed -n 's/^worktree //p' | head -1)"
  [ -n "$MAIN_ROOT" ] || warn_exit "main 체크아웃을 찾지 못함 — 보류"
  TARGET_ROOT="$MAIN_ROOT"
  echo "[handoff] linked worktree — main 체크아웃($MAIN_ROOT)의 HANDOFF.md 를 커밋"
fi

[ -f "$TARGET_ROOT/HANDOFF.md" ] || warn_exit "HANDOFF.md 없음 ($TARGET_ROOT) — 커밋 생략"

WITH_FILE="$(git -C "$TARGET_ROOT" rev-parse --path-format=absolute --git-dir 2>/dev/null)/HANDOFF_WITH"
if [ -s "$WITH_FILE" ]; then
  while IFS= read -r w; do
    w="${w%$'\r'}"
    [ -n "$w" ] && WITH+=("$w")
  done < "$WITH_FILE"
fi
PATHS=(HANDOFF.md ${WITH[@]+"${WITH[@]}"})
if [ -z "$(git -C "$TARGET_ROOT" status --porcelain -- "${PATHS[@]}")" ]; then
  [ "$PUSH_ALL" = "1" ] || warn_exit "HANDOFF.md 변경 없음 — 커밋 생략"
  echo "[handoff] HANDOFF.md 변경 없음 — 커밋 생략, push 단계로 간다(--push-all)"
else
  git -C "$TARGET_ROOT" add -- "${PATHS[@]}" 2>/dev/null \
    || warn_exit "add 실패 — 커밋 생략"

  # 기기 레이블: 한글 hostname 이 CP949 로 들어가 커밋 메시지가 깨진 실측(2026-07-27) — ASCII 만 남기고,
  # 비면 OS 이름. handoff_merge.py 블록 머리(platform.system)와 같은 이름을 쓴다(2026-11-07 — 커밋은
  # MINGW64_NT-10.0-26200, 블록은 Windows 로 갈라져 있었다).
  HOST="$(hostname 2>/dev/null | LC_ALL=C tr -cd 'A-Za-z0-9._-')"
  if [ -z "$HOST" ]; then
    case "$(uname -s 2>/dev/null)" in
      MINGW*|MSYS*|CYGWIN*) HOST=Windows ;;
      Darwin) HOST=Darwin ;;
      Linux) HOST=Linux ;;
      *) HOST=machine ;;
    esac
  fi
  STAMP="$(date +%Y-%m-%d) $HOST"
  MSG_FILE="$(git -C "$TARGET_ROOT" rev-parse --path-format=absolute --git-dir 2>/dev/null)/HANDOFF_COMMIT_MSG"
  COMMIT_ARGS=(-m "chore(handoff): 세션 핸드오프 갱신 ($STAMP)")
  if [ -s "$MSG_FILE" ]; then
    COMMIT_ARGS+=(-m "$(cat "$MSG_FILE")")
  fi
  if ! COMMIT_OUT="$(git -C "$TARGET_ROOT" commit "${COMMIT_ARGS[@]}" -- "${PATHS[@]}" 2>&1)"; then
    # 훅 출력(원인)을 끝 40줄까지 stderr 로 보인다 — 5줄로 자르면 사유가 안 보여 헤맨 실측(2026-11-08).
    # 레포 정책을 우회하는 env 는 자동으로 주지 않는다.
    printf '%s\n' "$COMMIT_OUT" | tail -n 40 | sed 's/^/[handoff]   /' >&2
    warn_exit "커밋 실패(훅 거부 등) — 수동 확인 필요"
  fi
  rm -f "$MSG_FILE" "$WITH_FILE"
  echo "[handoff] 커밋 완료: ${PATHS[*]} ($(git -C "$TARGET_ROOT" rev-parse --short HEAD))"
fi

if [ "$NO_PUSH" = "1" ]; then
  warn_exit "--no-push — 로컬 커밋만 (끝낼 때 push)"
fi
if [ -z "$(git -C "$TARGET_ROOT" remote 2>/dev/null)" ]; then
  warn_exit "remote 없음 — 로컬 커밋만 (push 생략)"
fi
if [ "$PUSH_ALL" = "0" ] && git -C "$TARGET_ROOT" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  FOREIGN="$(git -C "$TARGET_ROOT" log --format='%h %s' '@{u}..HEAD' 2>/dev/null | grep -v -E '^[0-9a-f]+ chore\((handoff|hygiene)\)' || true)"
  if [ -n "$FOREIGN" ]; then
    N="$(printf '%s\n' "$FOREIGN" | wc -l | tr -d ' ')"
    echo "[handoff] push 보류 — 핸드오프·위생 밖 커밋 ${N}건이 앞서 있다(다른 세션 것일 수 있다):"
    printf '%s\n' "$FOREIGN" | head -10 | sed 's/^/[handoff]   /'
    warn_exit "이 세션 커밋이면 --push-all 로 다시 돌린다. 아니면 그 세션이 push 할 때 같이 올라간다 — 로컬 커밋은 완료"
  fi
fi
if git -C "$TARGET_ROOT" push >/dev/null 2>&1; then
  echo "[handoff] push 완료 — 다른 기기에서 pull 하면 이어받음"
else
  warn_exit "push 실패(오프라인·인증·upstream 미설정 가능) — 로컬 커밋은 완료, 나중에 push 필요"
fi
exit 0
