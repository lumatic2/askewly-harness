#!/usr/bin/env bash
# Askewly Harness 스킬을 Claude Code (그리고 --codex 시 Codex) 에 설치.
#
# 사용:
#   bash install.sh           # ~/.claude/skills/ 에 설치
#   bash install.sh --codex   # ~/.codex/skills/ 에도 추가 설치
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/skills"
SKILLS=(harness harness-bootstrap)

WITH_CODEX=0
[[ "${1:-}" == "--codex" ]] && WITH_CODEX=1

install_into() {
  local dest="$1"
  mkdir -p "$dest"
  for s in "${SKILLS[@]}"; do
    rm -rf "$dest/$s"
    cp -r "$SRC/$s" "$dest/$s"
    echo "[ok] $dest/$s"
  done
}

install_into "$HOME/.claude/skills"
[[ $WITH_CODEX -eq 1 ]] && install_into "$HOME/.codex/skills"

# 엔진 스크립트 실행 권한
chmod +x "$HOME/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh" 2>/dev/null || true

echo ""
echo "설치 완료. Claude Code 세션을 새로 열면 /harness, /harness-bootstrap 이 잡힌다."
