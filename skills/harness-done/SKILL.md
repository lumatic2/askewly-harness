---
name: harness-done
description: >-
  하네스 흐름 3/3 — 완료. milestone 완료 판정→완료 보고서→report_close→ROADMAP 갱신→다음 milestone 연쇄까지의 마감 의식을 담당한다. 사용자가 "/harness-done", "하네스 마감", "milestone 닫아줘", "완료 보고서 써줘"라고 말하거나, /harness-run 이 milestone DoD 를 충족한 완료 경계에서 사용한다. 실행은 /harness-run, 새 계획은 /harness-plan, 주기 감사는 /harness-review.
---

# /harness-done — 완료 판정 → 마감 → 되먹임

> 하네스 3종 세트의 완료 단계: `harness-plan`(계획) → `harness-run`(실행) → **`harness-done`**. 셋은 한 세트다 — 함께 배포·토글한다.
>
> **기계장치는 한 곳** — 커맨드의 `$HARNESS_SCRIPTS` 해석:
> ```bash
> HARNESS_SCRIPTS="$HOME/.codex/skills/harness-run/scripts"
> [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness-run/scripts"
> ```

## Milestone 완료 hook (완료 경계 순서)

**검증 *실행*은 다이어트 대상이 아니다** — 의식은 줄여도 DoD 검증과 실표면 스모크는 실제로 돌린다(/harness-run 소유).

1. milestone `DoD` 를 evidence path 로 충족 확인 (관련 gate 전부 PASS).
   - **완료 감사 2문 (2026-07-31 kit 이식)**, DoD 확인 자리에서: ① **드리프트** — 계획·결정 로그 대비 벗어남(확장·누락 양방향) 없나 ② **순조로움 의심** — 무마찰 구간 하나 재검증(무마찰은 검증 부재 신호일 수 있다). **증거로 게이트를 인용했으면 그중 이번 변경을 가장 직접 겨냥한 하나를 재검증 대상에 반드시 포함한다** (M25 2026-08-22 — 무마찰 구간 하나로 갈음하면 인용한 게이트가 정말 이번 변경을 덮었는지는 끝까지 안 본다. 게이트 PASS 의 사정거리가 주장의 사정거리에 못 미치는 실패가 반복 관측됐다 — kg `gate-pass-scope-must-cover-the-claim`). 발견은 보고서 §이슈에, 실재하면 완료 전 수습 또는 partial.
2. **코드 리뷰 1회 — 이 milestone 이 만든 소스 변경을 대상으로.** `/code-review` 를 부른다(새 정의를 만들지 않고 기존 표면을 쓴다). 배치·주체·강제의 근거는 `the-orchestration-repo/docs/agent-os/research/2026-08-17-verifier-role-necessity.md` §2-5 가 소유한다 — 여기 옮겨 적지 않는다.
   - **대상 범위를 인자로 묶는다**: `/code-review <milestone 시작 직전 커밋>..HEAD`. 승인 커밋이 milestone 의 시작점이므로 그 부모가 base 다. 범위를 안 주면 리뷰가 번져 비용이 몇 배로 샌다(외부 실측).
   - **소스 변경이 없으면 생략한다.** 소스 = 코드·스크립트·훅·스킬 절차 파일. 산문 문서·마커만 바뀐 milestone 은 빈 리뷰가 되므로 부르지 않는다.
   - **Codex 런타임에는 대응 커맨드가 없다** — 건너뛴다. 배포본은 두 런타임에 같은 파일로 나가므로 이 분기가 필요하다.
   - **milestone 소스가 세션 레포 밖에 살면 이 호출은 성립하지 않는다.** 빌트인 `/code-review` 는 현재 세션 레포 컨텍스트 한정으로 동작한다(공식 문서에 교차 레포 언급 없음 · M18 실측 2026-08-22: 타 레포 범위 인자 2회 모두 본문 없는 즉시 반환). 그 리뷰는 소스 레포에서 여는 세션 몫으로 넘기고 여기서는 생략한다.
   - 발견의 처분은 사람 게이트다. 고칠 것은 완료 전에 수습하고, 남길 것은 보고서 §이슈나 finding 큐로 넘긴다. `--fix` 자동 적용은 기본이 아니다.
   - **훅으로 강제하지 않는다.** 리뷰 판정은 비결정론적이라 게이트로 만들면 오탐이 정당한 마감을 막고 규약이 우회된다(KG `deterministic-verification-gate-design-checklist`). 지켜졌는지는 아래 보고서의 `리뷰:` 줄로만 확인한다.
3. **완료 노트 = 완료 의식의 정본.** `templates/REPORT_TEMPLATE.md` **3섹션**(결과 / 이슈와 해결 / 증거)으로 `archive/reports/<date>-<id>-<slug>.md` 를 쓴다. **짧게 쓴다** — 설계 논거·경위는 changeset 과 커밋 메시지에 있고 여기 옮기지 않는다(CF6 2026-07-22: 구 7섹션 중 4개는 아무도 안 읽었다). §3 에 크기 회고·검증 관측을 적되 **`실표면:`**(사용자가 만지는 표면을 실제로 두드린 결과, 없으면 `none — <이유>`)·**`재현:`** 줄은 필수다. **`리뷰:`** 줄도 규약으로 남긴다(스크립트가 거부하지는 않는다) — 호출 인자와 지적 건수·처분, 또는 `리뷰: none — 소스 변경 없음` · `리뷰: none — 런타임 미지원(codex)` · `리뷰: none — 교차 레포 미지원(소스=<레포>, 그 레포 세션 몫)`. 이번 milestone 이 장치(스크립트·훅·명령)를 **신설**했으면 **`배선:`**(누가 언제 호출하나 + 실발화 1회 증거) 줄도 필수 — 만들었다≠호출된다(M10, kg mechanism-wiring-completion-rule. 실측: rotate 13일 미배선). 신설 장치 없으면 `배선: none — 장치 신설 없음`. **`수확:`**(kg 승격 후보 — 아래 인입 불릿의 3기준을 통과한 것만, 최대 2건) 줄도 필수다. 후보 0건이 정상 기본값이므로 `수확: 없음` 또는 `수확: 없음 — <이유>` 로 적는다 — **줄 자체가 없으면 스크립트가 거부한다**(M6 2026-08-20: 비강제 규약이던 시절 빠뜨림이 관측되지 않았다).
4. `python "$HARNESS_SCRIPTS/report_close.py" <report> --task-id <id> --root . --summary "<사용자용 한 문장>"` — ledger 파생·completion_summary·work `completed` 전환까지 1커맨드. 빈 보고서나 `실표면:`/`재현:`/`수확:` 누락은 스크립트가 거부한다. **평가 못 한 검사는 통과가 아니다 (2026-07-23 OI3)** — 증거에 "측정 불가·확인 못 함" 류가 있으면 `평가 못 함: <무엇을 왜 못 쟀나>` 줄로 표면화해야 닫힌다. `실표면:` 이 부작용("에러가 안 났다"·"파일이 생겼다")으로 통과를 주장해도 거부한다 — assertion 이 실제로 평가돼 성공을 보고했을 때만 통과다. **보고서 경로가 gitignore 로 추적 불가여도 거부한다**(로컬 유실 방지, 2026-07-23) — 이때는 `fix_report_durability.py --root . --apply` 로 예외를 넣고 다시 닫는다. `.harness/` 없는 레포는 보고서만 남긴다.
   > **이 커맨드가 하지 않는 일** (2026-08-06 외부 감사 #3): DoD 를 **재실행하지 않는다.** 보고서 산문을 읽어 형식을 검사할 뿐이고, 파생되는 `adversarial_verify` 이벤트의 `verdict: confirmed` 는 하드코딩 상수다 — 원장에 적힌 검증은 *이 스크립트가 수행한 것이 아니라* 보고서가 주장한 것을 옮긴 것이다. 검증을 실제로 돌리는 것은 1단계와 `/harness-run` 이고, 이 게이트가 막는 것은 **조용히 통과하는 것**뿐이다. 원장을 나중에 증거로 읽을 때 이 차이를 잊지 말 것.
5. `roadmap_sync.py complete` → `compact --max-lines 150` → `gap-check`(active milestone 0 이면 gap 요약 — 구명 horizon-check 삭제 2026-07-24).
   > **`complete` 는 블록을 `## Completed` 로 옮기기까지 한다** (M5 2026-08-20). 닫는 순간이 옮길 시점이라 별도 명령을 부르지 않아도 된다. 대상 섹션이 없으면 마지막 진행 섹션 뒤에 만들고, 섹션 **끝**에 붙이므로 `compact` 가 오래된 것부터 걷어내는 순서는 그대로다. 마커를 지우거나 BACKLOG 에 쓰지 않는다 — 그건 `compact` 의 다른 처분이다. **이미 닫혀 진행 섹션에 남아 있는 것들**(플릿 실측 32 레포 165건)은 `roadmap_sync.py relocate [--dry-run]` 이 소급 진입점이다.
6. **`python ~/.codex/hooks/harness_work_state.py next-chained --root .` — 승인 이력 있는 다음 milestone 이 남았으면 그 자리에서 이어간다** (marker active + approve 등록 = 승인의 *집행*). exit 1 이면 멈춘다. 후보 = 계획서 + 승인 이력(영수증 또는 `--chain`, FA1). `미승인 후보` 출력은 초안 — 자동 승인 금지, `/harness-plan` 으로.
   > 왜 단계인가: Stop hook 도 이 판정을 하지만 `stop_hook_active`(무한루프 방지) 탓에 **milestone 을 최대 한 개만 더 밀어준다**(2026-07-23 실측: 5연쇄가 OI2→OI3 에서 정지). **연쇄를 훅 발화 횟수에 의존시키지 않는다** — 완료 절차가 직접 묻는다.

- **kg 승격 후보 인입 (2026-07-31 사용자 결정)**: 완료 보고서 §이슈와 해결·finding 큐에서 ① 레포 밖에서도 유효하고(일반성) ② 다음에 시간을 아껴줄 검증된 규칙·패턴이며(재사용성) ③ 출처(재현 명령·URL·실측 커밋)를 한 줄로 적을 수 있는 것만 골라, kg 스킬 Add / Intake Workflow 정본 절차로 넣는다(discover 중복 확인 → 분류 → 노드 생성 → validate, 기본 `status: draft` — active 승격은 draft-review 게이트만). **후보 0건이 정상 기본값**, milestone 당 최대 2건. **판정 결과를 적는 자리는 보고서 §3 의 `수확:` 줄 하나다**(위 3단계) — 그 줄이 없으면 `report_close.py` 가 거부한다. 여기서 판정 기준을 다시 정하지 않는다.
- 완료된 계획서는 `archive/plans/` 로 이동한다(record 동결 — 옛 백링크는 정정하지 않는다).
- 보고서 제시는 **md 정본 경로 + 본문 요약**. Artifact 렌더 안 한다.
- **`active_work_id` 는 비우지 않는다** — Stop hook 완료 알림이 이 포인터를 읽는다(다음 approve 가 자연 갱신).
- **예외(high-risk — 보안·결제·마이그레이션·대규모 diff·배포면)**: spec/quality 2축 + near-miss 기록이 필요해 `ledger_append.py close` 경로를 유지. (구 `/harness` 승계 — 3분할 2026-07-24 이월. 2026-08-15 M20 감사: high-risk milestone 미발생으로 실발화 0 — 기회 부재이므로 유지)
- 크기 회고: milestone 이 changeset 1개로 닫혔으면 그건 step 이었다 — 보고서에 라벨 정합 적발 한 줄. 목표가 남았는데 연쇄 없는 1-milestone 승인으로 끝난 계획은 **과소 그릇 신호**로 한 줄 추가 — 목표 자체가 그 크기였다면 해당 없음(2026-07-31 목표 단위 계획 규약).

## ROADMAP lifecycle (상위 status machine)

`ROADMAP.md` 는 **milestone 상태만 관리하는 상위 장부**다 — 진행의 쓰기 정본은 plan doc 체크박스이고 이건 거기서 파생된다. `docs/BACKLOG.md`(구 레포는 루트 `BACKLOG.md`)는 완료·보류·아카이브된 milestone 의 압축 이력 저장소다.

역할 분담과 **문서 수명(living vs record)** 의 정본은 `/harness-plan` 배치 규약 표다. 핵심: `ROADMAP.md`=상태판(150줄 이하) · 계획서=계획 · 기록(record)은 완료 경계에 동결하고 **정정은 수정이 아니라 새 기록 추가** · 살아있는 문서의 stale 화가 기록화보다 나쁘다(발견 즉시 갱신).

**`ROADMAP.md` 표준 marker 형식** — `harness:goal` 줄(북극성 한 줄 요약) + `harness:milestone` block(`DoD`·`Evidence`·`Gap`·`Status: [ ]` 필수, 선택 `Plan`). **형식 정본은 부트스트랩이 실제로 찍는 것**: 번들 `init-ai-readiness.sh` 의 ROADMAP 스켈레톤. ⚠ **태그명과 필드 키워드를 바꾸지 않는다** — 이 마커를 파싱하는 도구는 이름이 바뀌면 예외 없이 조용히 빈 결과를 낸다.

규칙:
- `DoD` 와 `Evidence` 없는 milestone 은 자동 완료 처리 금지. checkbox 만으로 완료 판단하지 않는다.
- `blocked`/`error` 는 완료 처리 금지. 필요하면 해당 milestone block 에 `- Blocked by: ...` 를 남기고 멈춘다.
- 작업 중 step 진행률은 plan doc 체크박스에 기록하고, `ROADMAP.md` 는 milestone boundary 에서만 갱신한다.
- **계획 문서 사슬 — 2계층:** `CLAUDE.md` 「북극성」 절 → `plans/<date>-<milestone-id>-<slug>.md` → step 체크박스 (위→아래 링크). horizon 문서 층은 2026-07-23 재조립 C4·C9 로 폐지됐고 `harness:goal` 줄은 북극성 한 줄 요약으로 남는다(마커 문법은 22개 레포 총괄 계약이라 불변). 진행 상태의 쓰기 정본은 **plan doc 의 step 체크박스**다 — ROADMAP·`work.json` 은 거기서 파생되는 포인터이고, 어긋나면 plan 이 이긴다. 계획서가 없는 레포는 ROADMAP 만으로도 동작(optional).
- `ROADMAP.md` 는 150줄 이하를 유지한다. 초과 시 완료된 milestone 부터 `docs/BACKLOG.md` 로 3~5줄 압축 아카이브한다. active/pending milestone 은 자동 삭제 금지.
- candidate 가 단일 컴포넌트/좁은 smoke 라면 milestone 으로 승격하지 말고 step 으로 남긴다. active 후보는 최소 2-5 steps 와 하나 이상의 통합 smoke 가 자연스러워야 한다.

공통 helper: `python "$HARNESS_SCRIPTS/roadmap_sync.py" status | complete --milestone <ID> --evidence <path> --summary "<한 줄>" | compact --max-lines 150 --backlog docs/BACKLOG.md | gap-check`(구 레포는 `--backlog BACKLOG.md` 명시).

## Milestone 연쇄 (기본)

(도입: 3분할 2026-07-24 이월 — 사용자 선호 확정 규약) 승인된 계획 안에서는 milestone 완료 boundary 에서 **멈추지 않고**, ROADMAP 의 다음 pending/Next Candidate(`DoD`·`Evidence`·`Gap` 완비 + 결정 로그상 새 사용자 결정 불요) 1개를 자동 승격해 연쇄 진행한다 — 사용자 선호: 계획은 단단히, 실행은 끊김 없이. **정지 조건**: ① 사용자 소유 결정·secret·risk gate 출현 ② blocked/error ③ 승격 가능 후보 없음 ④ 사용자가 "하나만"·"여기까지" 명시. **새 milestone 을 *작성*해야 하면** 여전히 정지 → `/harness-plan` 계획 작성. **연쇄 중 승격된 milestone 이 새 plan doc 을 펼치면, 정지 없이 진행하되 그 계획(산문 요약+step 트리+결정 로그)을 진행 보고에 반드시 제시한다 — 결정 로그에 새 사용자 결정이 있으면 제시가 아니라 정지.**

후보 소진(active 0 + 승격 가능 0)이면 멈춘다 — 새 방향은 `/harness-plan`.
