---
name: session-end
description: >-
  세션 마무리 시 ROADMAP.md·cascade는 읽기만 하고 git-tracked HANDOFF.md 핸드오프(단독 커밋+push)와 저널를 append하는 스킬. "오늘 마무리할게", "세션 끝내자", "작업 끝났어", "/session-end"에 사용한다. ROADMAP milestone·compact·BACKLOG archive는 /harness-done이 담당하고, "로그만"·"append만"·"로드맵은 건드리지 말고"는 session-log가 담당한다.
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
codex: true
---

세션을 마무리한다. 아래 4단계를 순서대로 실행한다.

## 파일과 역할

| 파일 | 역할 | 쓰기 방식 |
|---|---|---|
| `$HARNESS_JOURNAL_DIR` | 저널 — 나중에 질문할 작업 이력·증거 | **append** |
| `HANDOFF.md` (레포 루트, **git-tracked**) | 핸드오프 — 다음 세션이 즉시 이어받을 것. 기기 간에는 git 으로 흐른다 | **overwrite**, 30줄 상한, 헬퍼가 **단독 커밋+push** |
| `CLAUDE.local.md` (gitignored) | **기기-로컬 사실만** (이 기기에서만 참인 경로·데몬 상태 등). 없으면 두지 않는 선택 파일 | 있을 때만 갱신 |
| `ROADMAP.md` + cascade docs | 현재 milestone 상태판 | **read-only** |

**ROADMAP·cascade 는 읽기만 한다.** 생성·편집, `Status: [x]`·`status="completed"` 변경, compact, BACKLOG archive는 전부 하네스 흐름(`/harness-done`) 소유다. 반영이 필요해 보이면 고치지 말고 `HANDOFF.md` 주의점에 한 줄로 남긴다 (예: "M2 DoD 충족된 듯 — 다음 /harness-done 에서 확인").

**BACKLOG 아카이브 = ROADMAP 에서 마커째 제거** (M3 2026-08-19 확정). `docs/BACKLOG.md` 로 아카이브된 milestone 은 ROADMAP 에 completed 마커를 남기지 않는다 — `/harness-done` 의 `roadmap_sync.py compact` 가 블록을 삭제하고 BACKLOG 에 4줄 요약을 append 하기 때문이다. 그래서 **ROADMAP 에 남아 있는 completed 마커는 "아직 아카이브되지 않은 것"** 이고, 그것이 진행 섹션(Active·Pending)에 앉아 있으면 위생 문제다(아래 1-c ①). compact 는 150줄 상한을 넘긴 만큼만 오래된 것부터 걷어내므로, 같은 ROADMAP 에 마커 없는 milestone 과 completed 마커가 공존하는 것은 불일치가 아니라 정상이다. 집행(제거·이동)은 `/harness-done` 소유이고 session-end 는 읽고 알리기만 한다.

**두 처분은 다른 명령이다** (M5 2026-08-20). *섹션 이동* = `roadmap_sync.py relocate`(마커를 남긴 채 자리만 옮긴다) · *BACKLOG 아카이브* = `roadmap_sync.py compact`(마커째 제거 + 4줄 요약 append). 전에는 이동 명령이 아예 없어서 위생 안내가 "손으로 하라"는 뜻이었고, 그래서 아무도 안 했다(플릿 실측 33 레포). 지금은 `complete()` 가 닫는 순간 자동으로 옮기므로 **새로 닫는 milestone 은 소급이 필요 없다** — `relocate` 는 이미 닫혀 있는 것들을 위한 진입점이다. 배치 판정 어휘(무엇이 진행 섹션인가)의 정본은 `roadmap_sync.py` 이고 `roadmap_hygiene.py` 가 그것을 import 한다. 사본을 두면 지적하는 것과 옮기는 것이 갈라진다.

**워크트리 규칙 (HO1 2026-07-27)**: linked worktree 세션이면 `HANDOFF.md` 를 **쓰지 않는다** — 레포 수준 핸드오프는 main 체크아웃 소유다. 이 세션의 이어받기는 active plan doc 의 진행 로그(append-only 절)에 남기고 브랜치를 push 한다(계획서가 브랜치에 실려 다른 기기에서도 이어받는다). 레포 수준으로 꼭 남길 말이 있으면 헬퍼 `--to-main` 으로 대필한다(아래 1-b — main 이 dirty 면 헬퍼가 보류한다).

## 1. read-only preflight → HANDOFF.md 갱신

읽을 것: **기존 `HANDOFF.md` 전문**(있으면 — ① Write 도구가 미독 파일 덮어쓰기를 거부하므로 Read 없이 Write 하면 매번 에러가 난다 ② 직전 핸드오프의 보류 후보·주의점을 읽고 승계/폐기를 판단해야 한다), `ROADMAP.md`(존재·harness marker·active milestone·150줄 초과 여부·BACKLOG 존재) 그리고 계획 계층이 있으면 top-down 으로 `CLAUDE.md` 「북극성」 절 → active milestone → active plan doc 의 step 트리 위치. cascade 파일이 없으면 그 블록 전체를 생략한다(ROADMAP-only 레포).

**첫 실행 이관**: `HANDOFF.md` 가 없고 `CLAUDE.local.md` 에 핸드오프("이어서 할 일" 등)가 있으면, 기기-무관 항목을 `HANDOFF.md` 로 옮긴다. `CLAUDE.local.md` 는 기기-로컬 사실만 남기고, 남는 게 없으면 파일을 지운다.

`HANDOFF.md` 는 Write 로 덮어쓴다. **핸드오프는 색인이지 사본이 아니다:**

1. **전체 30줄 상한.** 넘으면 항목을 지우지 말고, 레포 기록에 이미 있는 내용을 경로 포인터로 바꿔 줄인다.
2. **항목 자격 = 행동 가능.** "다음 세션이 이 줄만 읽고 시작할 수 있는가". 회고·성과 나열은 저널 소관이라 여기 금지.
3. **모호어 금지** — "테스트 마저" ❌ → "test_foo.py::test_bar 통과 — 현재 L42 AssertionError, fixture 가 None 인 게 원인 추정" ✅. 구체성과 30줄이 부딪히면 30줄이 우선하고 상세는 포인터로 내린다.
4. **훅이 계산하는 상태를 스냅샷으로 복사하지 않는다.** "N일+ 밀림" 같은 경과일수는 훅이 정본이라, 텍스트로 박아두면 상태가 바뀐 뒤에도 남아 다음 세션이 오판한다(2026-07-14 실측). 필요하면 "마지막 record YYYY-MM-DD" 같은 사실만 적는다.
5. **기기-로컬 사실은 여기 쓰지 않는다** — 이 파일은 다른 기기에서도 읽힌다. 이 기기에서만 참인 것은 `CLAUDE.local.md` 로.
6. **다른 레포의 상태를 여기서 관리하지 않는다** (2026-08-13). 이 파일은 *이 레포*의 핸드오프다. 타 레포를 언급해야 하면 `→ <repo>` 접두를 붙이고 **"그 레포 세션에서 확인"임이 드러나게** 쓴다 — 예: `→ aws-guide: 북극성 확정 여부는 그 레포 세션에서 확인`. 상태 단정(`북극성 미확정`·`milestone 없음`)은 쓰지 않는다.
   왜: 자기 레포 상태는 그 레포 세션이 갱신하지만 **여기 적힌 타 레포 문장은 갱신할 주체가 구조적으로 없다** — 쓰인 순간부터 낡기 시작하고, 다음 세션이 그걸 현재형으로 읽는다. (2026-08-13 실측 결함: 전날 핸드오프의 "aws-guide·askewly-security 북극성 미확정"이 하루 만에 거짓이 됐는데 아무도 못 고쳤고, 브리핑이 그대로 인용해 오보를 냈다.) 타 레포 상태의 실측 정본은 `portfolio_live.py` 의 `🧭 북극성이 비어 있는 레포` 줄과 `PORTFOLIO.generated.md` 다.

```markdown
## 이어서 할 일
> {today} 세션 종료 시 기록

- {파일 경로·명령·blocker 를 항목당 1~3줄. 보통 3~8개}

### 계획 위치 (cascade)   ← cascade docs 있을 때만
- 북극성: {한 줄}
- Milestone(active): {id} {제목} — Status, DoD 진행
- Step: {완료 x/y} · 다음 leaf {step-N}
- 다음 차례: {파일·명령 수준으로}

### 현재 상태 / 주의점
- {커밋·푸시 여부, 브랜치 상태 — 거의 항상 포함}
- {ROADMAP preflight 결과 중 다음 하네스 흐름(/harness-plan~done)이 처리할 것}
```

### 1-b. 핸드오프 커밋+push (헬퍼 소유)

```bash
bash ~/.claude/skills/session-end/bin/handoff_commit.sh
```

(Codex 배포본이면 `~/.codex/skills/...` — 경로만 다르고 동작 동일.) 헬퍼 계약: **HANDOFF.md 만 pathspec 커밋**하므로 다른 dirty·staged 변경은 절대 휩쓸리지 않는다 · push 실패(오프라인·인증)는 경고만 하고 exit 0 — 세션 마감을 막지 않는다 · linked worktree 면 쓰기를 거부한다(위 워크트리 규칙). 워크트리에서 레포 수준 메모가 꼭 필요할 때만: `bash .../handoff_commit.sh --to-main <<'EOF'` + 내용 + `EOF`.

한 줄로 보고한다 (예: `ROADMAP: read-only 확인 | HANDOFF.md: 이어서 할 일 5건, 커밋+push 완료`). ROADMAP 이 없으면 만들지 말고 `ROADMAP: 없음(read-only)`.

### 1-c. ROADMAP 위생 점검 (비파괴 — M3 2026-08-19)

```bash
python3 ~/.claude/skills/session-end/bin/roadmap_hygiene.py
```

(Codex 배포본이면 `~/.codex/skills/...`.) 읽기 전용이고 **항상 exit 0** 이다 — 이 점검이 세션 마감을 막는 일은 없다. 보는 것 4가지: ① 종결 마커가 진행 섹션(Active·Pending·Next·진행·대기·후보)에 남아 있음 ② 진행 중 milestone 0 ③ 마커 status ↔ 체크박스 불일치 ④ 비정본 status 어휘. 판정 어휘는 총괄 뷰 스크립트(`portfolio_status.py`)를 그대로 불러 쓰므로 총괄과 같은 눈으로 본다.

- **깨끗하면 `ROADMAP 위생: PASS (active N)` 한 줄이다.** 그 한 줄은 4단계 완료 메시지에 흡수하고 따로 보고하지 않는다 — 통과 시 조용해야 사람이 이 스킬을 피하지 않는다.
- **발견이 있으면 출력을 그대로 사용자에게 보여준다.** 요약하지 말 것(경로·ID 가 곧 처분 대상이다).
- **고치는 것은 사용자 지시가 있을 때만.** ROADMAP read-only 계약은 그대로다 — 게이트는 목록과 제안만 낸다. 사용자가 그 자리에서 지시하면 그때 고치고, 지시가 없으면 `HANDOFF.md` 주의점에 한 줄로 넘긴다.
- **왜 여기 있나**: `/harness-done` 은 milestone 하나를 닫는 데까지만 책임지고 닫은 뒤 ROADMAP 전체 모양은 아무도 안 본다. 그래서 마지막 milestone 을 닫은 레포가 총괄 뷰에서 조용히 사라진다(2026-08-15 askewly-command 실측). 세션 단위로 반드시 지나가는 관문이 여기뿐이라 게이트를 여기 둔다.
- `roadmap_sync.py gap-check` 와 겹치지 않는다 — 그쪽은 하네스 마감이 부르는 gap 보고서(다음 milestone 후보 초안)이고, 이쪽은 세션 마감이 부르는 **마커 결함 점검**이다.
- **진행 중 milestone 이 없는 것은 지적하지 않는다** (2026-08-20 사용자 확정). 다음이 있으면 그걸 하고 없으면 멈추는 것이며, 승격·PARK·kind 면제 중 무엇으로 보낼지는 **사용자 소유 판단**이다. 방치 여부는 주간 PORTFOLIO 리뷰의 판정 대기 큐가 이미 본다 — 매 세션 마감에 같은 처분을 요구하면 사람이 이 관문을 피하게 되고, 그러면 게이트가 있으나 없으나다(계약 ⓐ). 이 게이트가 내는 것은 **상태**가 아니라 **결함**뿐이다: 섹션 오배치 · 체크박스 불일치 · 비정본/누락 status 어휘.

## 2. 저널 기록 (append)

본문을 stdin 으로 헬퍼에 넘긴다. 헬퍼가 날짜·기기 레이블·파일명·헤더·append 를 처리한다. **이어할 일은 여기 쓰지 않는다**(핸드오프는 1단계 소관).

```bash
PYTHONIOENCODING=utf-8 python3 ~/.claude/skills/session-end/bin/session-log.py <<'BODY'
한 줄 요약
  {무엇이 실제로 바뀌었는지 한 문장}

한 일 / 증거
  - {한 항목에 작업 + 근거를 같이. 커밋 해시·경로·검증 결과·before/after 를 그 항목에 붙인다}
  - {같은 사실을 작업과 증거로 나눠 두 번 쓰지 않는다}

판단 / 배운 것
  {왜 A 대신 B 였는지, 문서·코드가 실제와 달랐던 점, 재사용 가능한 지식.
   이력서 문장으로 번역 가능한 사실도 여기 — 평가가 아니라 행동·숫자·결과로. 없으면 섹션 생략}

막힌 것 / 개선할 것
  - 막힌 것: {미해결 문제 — 시도한 것 + 왜 안 됐는지}
  - 개선할 것: {이번 산출물을 /pr-review 축으로 자기점검 — spec(요구·계획 대비 누락) / quality(정확성·유지보수성·보안·테스트 공백)}
  둘 다 없으면 섹션 생략. 실행 가능한 개선 지점은 1단계 `이어서 할 일` 로도 넘긴다
BODY
```

**작성 기준**
- **필수는 앞 2개 섹션.** 뒤 2개는 내용이 있을 때만 — 채우려고 늘리지 않는다.
- **적을 것**: 나중에 근거가 될 사실(커밋·숫자·before/after), 판단과 그 이유, 비자명한 발견(drift·함정).
- **뺄 것**: 자명한 과정 나열("파일 읽음"·"grep 함"), 커밋 메시지·diff 에 이미 남는 내용의 재진술.
- 길이는 세션의 증거량에 맞춘다. 판정 기준 = "이 로그만 보고 무엇을 했고 어떤 증거가 남았는지 복원 가능한가".

## 3. 출력

**bash 출력은 사용자 화면에 보이지 않는다.** 아래 셋을 최종 답변 본문에 직접 출력해야 사용자가 확인할 수 있다. "저널 에 남겼다"는 요약으로 대체하면 사용자는 아무것도 못 본다.

1. **저널 저널 블록** — 헬퍼 stdout 의 `── 기록한 세션 … ──` 부터 `✓ … 기록 완료 (append)` 까지 그대로. 재타이핑하면 기록물과 어긋난다.
2. **이어서 할 일 echo** — 1단계에서 `HANDOFF.md` 에 쓴 리스트 재출력(실체는 그 파일에만 있고 여기선 확인용 표시일 뿐) + `handoff_commit.sh` 의 `[handoff]` 결과 줄.
3. **완료 메시지** — `저널 기록 완료 (append) | HANDOFF.md 핸드오프 갱신·커밋·push | ROADMAP read-only 확인 · 위생 <PASS(active N) | 발견 N건 | 생략>`. 위생 발견이 있으면 이 줄로 갈음하지 말고 1-c 출력 전문을 함께 보여준다.
