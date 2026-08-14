#!/usr/bin/env bash
# Askewly Harness 스킬을 Claude Code (그리고 --codex 시 Codex) 에 설치.
#
# 사용:
#   bash install.sh           # ~/.claude/skills/ 에 설치
#   bash install.sh --codex   # ~/.codex/skills/ 에도 추가 설치
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/skills"
SKILLS=(harness-plan harness-run harness-done harness-bootstrap session-end session-log)
# 구판(단일 /harness 스킬) 잔재 — 남아 있으면 신판과 라우팅이 섞인다
LEGACY=(harness)

WITH_CODEX=0
[[ "${1:-}" == "--codex" ]] && WITH_CODEX=1

install_into() {
  local dest="$1"
  mkdir -p "$dest"
  for s in "${LEGACY[@]}"; do
    if [[ -d "$dest/$s" ]]; then
      rm -rf "$dest/$s"
      echo "[removed] $dest/$s (구판 잔재)"
    fi
  done
  for s in "${SKILLS[@]}"; do
    rm -rf "$dest/$s"
    cp -r "$SRC/$s" "$dest/$s"
    echo "[ok] $dest/$s"
  done
  chmod +x "$dest/harness-bootstrap/scripts/init-ai-readiness.sh" 2>/dev/null || true
}

install_into "$HOME/.claude/skills"
[[ $WITH_CODEX -eq 1 ]] && install_into "$HOME/.codex/skills"

echo ""
echo "설치 완료. 새 세션에서 /harness-bootstrap → /harness-plan → /harness-run → /harness-done 이 잡힌다."
