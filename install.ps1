# Askewly Harness 스킬을 Claude Code (그리고 -Codex 시 Codex) 에 설치.
#
# 사용:
#   ./install.ps1            # ~\.claude\skills\ 에 설치
#   ./install.ps1 -Codex     # ~\.codex\skills\ 에도 추가 설치
param([switch]$Codex)

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "skills"
$skills = @("harness-plan", "harness-run", "harness-done", "harness-bootstrap", "session-end", "session-log")
# 구판(단일 /harness 스킬) 잔재 — 남아 있으면 신판과 라우팅이 섞인다
$legacy = @("harness")

function Install-Into($dest) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($s in $legacy) {
    $target = Join-Path $dest $s
    if (Test-Path $target) {
      Remove-Item -Recurse -Force $target
      Write-Host "[removed] $target (구판 잔재)"
    }
  }
  foreach ($s in $skills) {
    $target = Join-Path $dest $s
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse (Join-Path $src $s) $target
    Write-Host "[ok] $target"
  }
}

Install-Into (Join-Path $HOME ".claude\skills")
if ($Codex) { Install-Into (Join-Path $HOME ".codex\skills") }

Write-Host ""
Write-Host "설치 완료. 새 세션에서 /harness-bootstrap → /harness-plan → /harness-run → /harness-done 이 잡힌다."
