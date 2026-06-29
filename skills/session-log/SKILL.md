---
name: session-log
description: >-
  세션 기록을 vault 40-Logs 일일 로그에 append만 하는 경량 마감 스킬. ROADMAP.md, CLAUDE.local.md, AGENTS.md, README.md 등 레포 파일은 절대 만들거나 수정하지 않는다. 한 레포에서 여러 터미널·여러 에이전트 세션을 병렬로 진행할 때 전체 핸드오프 파일이 흔들리지 않도록, append-only 저널 기록만 남기고 방금 기록한 내용을 사용자에게 그대로 출력한다. 사용자가 "로그만 남겨줘", "가볍게 마무리", "append만", "세션 기록만", "session-end-light", "session-log", "vault 40-Logs에만 남겨", "로드맵은 건드리지 말고 마무리"라고 말할 때 반드시 이 스킬을 사용하라. 전체 마감(ROADMAP 갱신 + CLAUDE.local.md 핸드오프 + vault 로그)이 필요하면 session-end를 사용한다.
allowed-tools:
  - Bash
  - Read
codex: true
---

# session-log

세션을 **vault 40-Logs에 append만** 하고 끝낸다.

## 역할

이 스킬은 `session-end`의 경량 버전이다. 여러 터미널이 같은 레포에서 동시에 일할 때 `ROADMAP.md`나 `CLAUDE.local.md`를 각 세션이 덮어쓰면 상태가 흔들린다. 그래서 이 스킬은 세션별 저널만 누적한다.

## 절대 하지 않는 것

- `ROADMAP.md` 생성·수정·정리
- `CLAUDE.local.md` 생성·수정·덮어쓰기
- `AGENTS.md`, `CLAUDE.md`, `README.md` 등 레포 문서 수정
- git commit, branch 정리, 배포, 포맷팅 같은 repo bookkeeping
- vault daily log 외의 새 vault 노트 생성

필요한 것이 위 작업 중 하나라면 이 스킬이 아니라 `session-end`, `roadmap-update`, `vault-write` 등 더 맞는 스킬을 사용한다.

## 기록 대상

헬퍼가 현재 날짜와 기기 레이블을 판단해 아래 파일에 append한다.

```text
~/vault/40-Logs/YYYY-MM-DD.md
```

파일이 없으면 헬퍼가 frontmatter와 제목을 만들고, 있으면 끝에 새 세션 블록만 붙인다.

> 저널 디렉터리는 기본 `~/vault/40-Logs/` 이고, `HARNESS_JOURNAL_DIR` 환경변수로 바꿀 수 있다.

## 실행 절차

1. 현재 세션에서 실제로 한 일과 막힌 것을 짧게 정리한다.
2. repo 파일을 읽어야 할 때는 필요한 만큼만 읽는다. 수정하지 않는다.
3. 아래 헬퍼에 본문을 stdin으로 넘긴다.

```bash
PYTHONIOENCODING=utf-8 python3 ~/.claude/skills/session-log/bin/session-log.py <<'BODY'
한 일
  {무엇을 했는지. 대상 파일, 판단, 검증 결과를 포함한다.}

막힌 것
  {미해결 문제가 있으면 적는다. 없으면 이 항목은 생략한다.}

책 메모
  {나중에 회고나 글감으로 남길 만한 관찰. 없으면 "없음".}
BODY
```

Codex 환경에서 `~/.claude/skills/session-log/bin/session-log.py`가 없고 repo-local 스킬 디렉터리에서 실행 중이면 다음 fallback을 사용한다.

```bash
PYTHONIOENCODING=utf-8 python3 session-log/bin/session-log.py <<'BODY'
...
BODY
```

## 출력

헬퍼 stdout을 **최종 답변에 그대로 포함한다.** 헬퍼는 방금 append한 블록을 다시 출력하므로, 모델이 기록물을 재타이핑해 drift를 만들지 않아야 한다.

중요:
- 기록 내용을 "저장했다"는 요약만 말하고 끝내지 않는다.
- `── 기록한 세션 ... ──` 블록부터 `✓ ... 기록 완료 (append)` 줄까지 빠짐없이 보여준다.
- 사용자가 바로 확인할 수 있도록, 완료 문장보다 기록 블록을 먼저 출력한다.

마지막에 이 고정 문장을 붙인다.

```text
vault 40-Logs 기록 완료 (append only)
```

## 사용 판단

- 사용자가 "로그만", "append만", "가볍게", "로드맵 건드리지 말고"라고 하면 이 스킬을 사용한다.
- 사용자가 "다음 세션 핸드오프", "ROADMAP 갱신", "전체 마감", "`/session-end`"라고 하면 `session-end`가 더 맞다.
- 사용자가 일반 지식 노트, 리서치 노트, 클리핑을 vault에 저장하라고 하면 `vault-write`가 더 맞다.
