# Askewly Harness

> AI 코딩 에이전트(Claude Code·Codex)가 **구조를 잃지 않고** 멀티스텝 작업을 이어가게 하는 하네스 스킬 패키지.

빈 레포에 협업 인프라를 깔고(`/harness-bootstrap`), 그 위에서 실제 작업을 갈래별 워크플로우로 실행한다(`/harness`).

## 왜 하네스인가

> **모델은 엔진이고, 하네스는 차의 나머지 전부다.**
> 핸들·브레이크·계기판·안전벨트·도로 표지판이 없으면 좋은 엔진도 좋은 시스템이 되지 않는다.

강한 모델을 그냥 풀어놓으면 큰 작업에서 방향을 잃는다. 하네스는 호출 *전에* 어떤 맥락·제약을 줄지, 호출 *후에* 어떤 검증·재시도·완료 조건을 적용할지를 파일과 규약으로 고정한다. 엔진을 바꾸지 않고 차를 잘 만드는 일이다.

## 들어 있는 것

**코어 — 부팅 + 실행**

| 스킬 | 역할 |
|---|---|
| **`/harness-bootstrap`** | 새(또는 기존) git 레포에 AI-readiness 인프라를 부팅한다 — `CLAUDE.md`, `AGENTS.md`, `ROADMAP.md`(150줄 budget), `BACKLOG.md`, `docs/adr/`, 갈래별 필수 파일, `.harness/manifest.json`. |
| **`/harness`** | 부팅된 레포에서 실제 작업을 **4갈래**(product / learning / tooling / workflow)로 실행한다. 갈래마다 진행 상태·검증·완료 조건이 다르고, 큰 작업은 step-leaf 루브릭으로 규모를 가른 뒤 `docs/plans/` 에 step 트리를 펼쳐 장시간 이어간다. |

**세션 마감 — 핸드오프 + 저널**

| 스킬 | 역할 |
|---|---|
| **`/session-end`** | 세션 마무리. ROADMAP 은 read-only 로 확인만, `CLAUDE.local.md` 핸드오프 덮어쓰기, 저널 디렉터리에 서사적 기록 append. 다음 세션이 곧장 이어받게 한다. |
| **`/session-log`** | `/session-end` 의 경량판 — 저널 append 만. 여러 터미널이 한 레포에서 병렬 작업할 때 핸드오프 파일을 안 건드리고 로그만 누적. |

## 설정 (환경변수, 둘 다 선택)

| 변수 | 기본값 | 용도 |
|---|---|---|
| `HARNESS_JOURNAL_DIR` | `~/vault/40-Logs` | session-end/log 가 쓰는 저널 디렉터리. Obsidian vault 가 없으면 원하는 경로로 지정. |
| `HARNESS_EVIDENCE_REPO` | (없음) | 여러 repo 의 하네스 작업을 모으는 중앙 evidence ledger repo. 설정 시 bootstrap·session-end 가 opt-in 으로 갱신. 미설정 시 조용히 skip. |

## 4갈래

| 갈래 | 무엇 | judge(완료 게이트) |
|---|---|---|
| **product** | 출시할 제품 (web/mobile/backend) | lint·테스트 통과 없이 "완료" 금지 |
| **learning** | 공부·리서치·레퍼런스 분석 | 5섹션 다 채우기 전 통찰 보고 금지, 인용은 출처+접근일 |
| **tooling** | 스킬·스크립트·런타임 유지보수 | targeted test/smoke/sync 증거 없이 완료 금지 |
| **workflow** | 반복 업무 자동화 | 외부 권위 인용 없는 수치·결론 금지 |

## 설치

```bash
# macOS / Linux / WSL
bash install.sh
```

```powershell
# Windows PowerShell
./install.ps1
```

스킬을 `~/.claude/skills/` 에 복사한다 (`--codex` 옵션 시 `~/.codex/skills/` 에도). 설치 후 Claude Code 를 재시작하거나 세션을 새로 열면 `/harness`, `/harness-bootstrap` 이 잡힌다.

## Quickstart

```bash
cd ~/projects/my-new-thing      # 빈 디렉터리여도 됨 (자동 git init)
# Claude Code 에서:
/harness-bootstrap              # 무엇을 만드는 레포냐 묻고 인프라 부팅
/harness                        # ROADMAP active milestone 부터 실제 작업 실행
```

bootstrap 없이 엔진 스크립트를 직접 부를 수도 있다 (Codex·CI 등):

```bash
bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh "$PWD" \
  --full --mode learning
```

## 구조

```text
skills/
  harness/              # 실행 워크플로우 (SKILL.md + references/ + scripts/)
  harness-bootstrap/    # 레포 부팅 (SKILL.md + scripts/init-ai-readiness.sh + templates/)
  session-end/          # 세션 마감 핸드오프 + 저널 (SKILL.md + bin/)
  session-log/          # 경량 저널 append (SKILL.md + bin/)
install.sh / install.ps1
```

## 출처·라이선스

- jha0313/harness_framework 의 PRD/ARCHITECTURE/ADR 템플릿 패러다임에서 출발해, 4갈래·judge 위치·planning cascade 로 확장.
- MIT License. [LICENSE](LICENSE) 참조.
