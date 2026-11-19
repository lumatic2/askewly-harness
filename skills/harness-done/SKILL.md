---
name: harness-done
description: >-
  하네스 흐름 3/3 — 완료. milestone 완료 판정·스위트 → 코드 리뷰 → 완료 노트 → 마감 감사 → 닫기(report_close·ROADMAP) → 다음 milestone 연쇄까지의 마감을 담당한다. 진입은 사용자가 `/harness-done` 을 직접 치거나 `/harness-run` 이 milestone DoD 를 충족한 완료 경계에서 넘길 때뿐이다 — 하네스 진입점은 /harness-plan(사용자가 슬래시나 말로 이름을 부른다)이고 이 스킬은 그 연속 단계라 모델이 잇는다. "마감해줘" 같은 자연어만으로 새로 켜지 않는다. 예외는 중단 종결 하나 — 사용자가 `/harness-done drop <id>` 를 치거나 "이 milestone 접자"·"M1 중단하자"처럼 외부 결과로 milestone 을 접겠다고 명시하면 중단 갈래로 진입한다(모델이 스스로 중단을 판정하지는 않는다). 실행은 /harness-run, 새 계획은 /harness-plan.
---

# /harness-done — 완료 판정 → 마감 → 연쇄

> 3종 세트: `harness-plan` → `harness-run` → **`harness-done`**. 기계장치 경로·세션 초점:
> ```bash
> ASKEWLY_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -d "$ASKEWLY_ROOT/skills" ] || ASKEWLY_ROOT="$(ls -d "${CODEX_HOME:-$HOME/.codex}"/plugins/cache/*/askewly/*/ 2>/dev/null | tail -1)"
> HARNESS_SCRIPTS="${ASKEWLY_ROOT%/}/skills/harness-run/scripts"
> HARNESS_ROOT="$(python "$HARNESS_SCRIPTS/harness_focus.py" resolve)"
> ```
> 의식은 줄여도 **검증 실행은 줄이지 않는다** — DoD 검증과 실표면 스모크는 실제로 돌린다.

## 완료 경계 순서

1. **DoD 확인 + 스위트** — milestone DoD 를 evidence 경로로 충족 확인(게이트 전부 PASS). 그 자리에서 1문: 계획·결정 로그 대비 벗어남(확장·누락)이 없나. 이어서 **2단계 리뷰를 먼저 받고, 지적 반영 커밋을 다 모은 뒤 스위트를 마감당 한 번 돌린다**(M32 V-2 — 마감 스위트는 유지하되 1회) — 리뷰를 기다리며 스위트를 같이 돌리면 지적을 코드로 반영하는 순간 그 실행이 무효가 되어 한 번 더 돈다(2026-11-19 M30 사용자 결정 — a-private-repo 한 마감에 3~4회 실측). 리뷰가 생략되는 마감(소스 변경 없음·교차 레포·Codex)은 바로 스위트를 돌린다. 레포의 push 훅이 같은 커밋의 통과 기록을 이미 남겼으면 `--check` 가 덮으므로 다시 돌리지 않는다.
   - **스위트**: `python <이 스킬 Base directory>/bin/suite_gate.py --root "$HARNESS_ROOT"`. 레포 테스트를 자동 감지해 실제로 돌리고 `.harness/suite-gate.json` 에 HEAD·exit code 를 남긴다. 레포의 정식 명령이 따로 있으면 `--command "<명령>"`. 실패면 고치고 커밋한 뒤 다시 돌린다 — 기록은 **코드 지문**에 묶여 있다(M32 V-1): 기록 전용 경로(`plans/`·`archive/plans/`·`changesets/`·`archive/reports/`·`docs/reports/`·`ROADMAP.md`·`HANDOFF.md`·`docs/BACKLOG.md`·`.harness/work.json`·`.harness/execution-ledger.jsonl`·`docs/known-failures.md`) 밖 트리가 같으면 기록 파일 커밋·리베이스·커밋 순서 뒤바뀜 뒤에도 그대로 덮는다(재실행 불필요). 그 밖의 파일이 바뀌면 재실행이 필요하다. 지문은 커밋 트리만 본다 — 기록 당시 미커밋 변경은 `--strict-clean` 이 따로 본다.
   - **선재 빨강(내 변경 탓이 아닌 실패)은 `--waive` 대신 알려진 실패 목록으로** (M32 V-4): 세션이 그 실패가 main(기준 브랜치)에서도 빨갛다는 것을 직접 재현하고, 레포 `docs/known-failures.md` 에 `- <실패 이름 일부> — <사유 + main 재현 증거> (<날짜>)` 한 줄을 올린 뒤 완료 노트 §3 에 넣은 줄을 그대로 적는다(사용자가 노트에서 뒤집는다). 스위트를 다시 돌리지 않고 `--check` 로 확인한다 — fail 기록의 실패 이름이 전부 목록 줄에 걸리면 `covered — 알려진 실패만 n건` 이고 `report_close` 도 면제 없이 닫는다. 목록 밖 실패가 하나라도 있거나, 실패 이름을 하나도 못 뽑았거나(pytest `FAILED`·`ERROR`·cargo `... FAILED`·TAP `not ok`·node `✖`·jest `FAIL` 밖의 출력), 뽑은 이름 수가 러너 요약의 실패 수와 다르거나, `-x`·`--maxfail` 등으로 중간에 멈춘 실행이거나, 실행 중 코드가 커밋된 실행이면 덮지 않는다. 목록 키는 실패 이름과 경계(`::`·`[`·끝)에서 맞아야 한다 — 부분 문자열(`test_x` 가 `test_x_new` 를)로는 덮지 않고, 6자 미만 키와 사유 구분자(` — `) 없는 줄은 무시한다. `--check` 가 「목록에서 지울 후보」를 찍으면 그 줄은 이번에 통과한 것이니 지운다. `--waive "<사유>"` 는 실패 이름을 뽑을 수 없는 플레이키·환경 실패에만 남기고, 쓰면 노트 §3 에 `스위트: waived — <사유>` 를 적는다. 몇 분 넘게 걸리는 스위트는 백그라운드로 돌린다. 제한 시간은 기본 3600초, `--timeout <초>`(또는 env `SUITE_GATE_TIMEOUT`)로 조정하고, 실패·시간 초과 시 끝 80줄이 출력된다. 성공도 포함한 전체 로그는 실행 중부터 `.harness/suite-gate.log` 에 남으며, 기록에 시작·완료 시각과 경과 시간이 포함된다. pytest는 `--command "python -m pytest -vv --durations=20"`처럼 현재 테스트와 시간을 보이게 한다. 실행 중에는 기록 파일 경로(위 목록) 밖의 커밋을 하지 않는다 — 기록 파일만 커밋했으면 시작·끝 지문이 같아 통과가 기록되지만, 그 밖이 바뀌면 `실행 중 HEAD 변경` 으로 fail 이다. 제한 시간을 넘기면 마지막 테스트를 분석하고 분할하며, 원인 확인 없이 같은 전체 명령 재시작·제한 시간 증가는 하지 않는다.
   - **통과 뒤 생긴 커밋(리뷰·감사 반영)이 위 기록 파일 경로만 바꿨으면(= 지문이 같으면) 스위트를 다시 돌리지 않는다. 그 밖의 파일을 바꿨으면 다시 돌린다.** 반영을 다 모은 뒤 한 번 돌리면 된다. 덮는지는 `python <이 스킬 Base directory>/bin/suite_gate.py --root "$HARNESS_ROOT" --check` 로 확인한다(실행 없이 판정만, 덮으면 exit 0).
   - **스위트 명령이 괄호 묶음**(`(cd a && …) && (cd b && …)` 같은 POSIX 복합 명령)이면 `--command "<명령>" --shell bash` 로 돌린다 — Windows 기본 셸에서는 실패한다.
   - **pre-push 훅 계약**: push 훅에는 전수 스위트를 두지 않는 것이 기본이다(M32 V-3 — a-private-repo 는 `lint`·`typecheck` 만, 30일 push 전수 검사의 코드 결함 0건·7.0h). 전수는 마감 스위트가 한 번 돈다. 그래도 레포의 push 훅이 같은 스위트를 돌린다면, 훅에서 `suite_gate.py --root <레포> --check --strict-clean --head <push 되는 sha> --base <원격 sha> --command "<훅이 돌리는 명령>"` 을 불러 exit 0 이면 건너뛴다. `--base` 는 훅 stdin 의 원격 sha 다 — 원격에 이미 있는 커밋 뒤로 기록 파일만 바뀐 push(다른 세션의 HANDOFF 한 줄 등)는 스위트 기록 없이도 덮는다(새 브랜치의 0 sha 는 그대로 넘겨도 된다 — 스크립트가 거르고 기록 판정으로 넘어간다). 기록 당시 추적 파일에 미커밋 변경이 있었으면(`--strict-clean`) 건너뛰지 않는다. `--command` 는 스위트를 돌릴 때 준 명령과 글자까지 같아야 한다. 훅이 전수 실행을 해야 할 때는 `suite_gate.py --root <레포> --command "<명령>" --stream` 으로 돌려 통과 기록을 남긴다 — 기록이 코드 지문에 묶여 있어 바로 뒤 마감 스위트와 다음 push 가 같은 코드면 그 기록으로 건너뛴다(리베이스 뒤에도).
2. **코드 리뷰 — 내장 한 자리.** 소스 변경(코드·스크립트·훅·스킬 절차 파일)이 있고 **소스가 세션 레포 안**이면 `/code-review medium <milestone 시작 직전 커밋>..HEAD`(강도는 **medium 고정** — high 를 쓰지 않는다, 2026-11-17 사용자 결정) 에 계획서 경로와 사용자 합격선 한 줄, 그리고 **「테스트 품질도 본다 — 계획서 `Verify` 의 단언이 테스트에 실제로 있는가, 구현을 그대로 베낀 단언(실제 동작을 정답으로 적은 것)·경계값 누락·약화된 기존 테스트가 있는가」** 를 붙여 돌린다(2026-10-13). 계획서에 `테스트 없음` leaf 가 있으면 그 사유가 맞는지도 리뷰 대상이다. 계획서 `마감 감사:` 가 **`안 함`일 때만** 프롬프트에 **명세 축 세 질문**도 붙인다 — `함`이면 감사자의 `완료`·`정합` 축이 같은 것을 보므로 빼서 리뷰를 정확성에 집중시킨다(2026-11-16 사용자 결정, ADR 0039. 질문은 2026-10-14 mattpocock 대조 흡수 — 정확성 축과 섞지 말고 따로 답하게 한다): ① 계획서 leaf `Artifact` 가 요구한 것 중 **빠졌거나 반만 된 것** ② 계획서가 **요청하지 않은 변경**(인접 리팩터·추가 기능·범위 밖 파일) ③ 구현된 것처럼 보이지만 **동작이 틀린 것**. 지적 처분은 완료 노트 `리뷰:` 줄에 축별로 적는다. 소스가 세션 레포 밖이면 내장은 구조적으로 못 보므로 **생략하고 4단계 감사자의 `교차` 축이 받는다**(노트에 `리뷰: none — 교차 레포` + 사유). 소스 변경이 없으면 생략.
   - **지적은 판결이 아니라 주장이다.** 리뷰어는 대화를 못 봤다 — 반영 전에 지적마다 계획서 결정 로그·사용자 합격선·레포 실물과 대조하고, 어긋나는 지적은 **기각 + 이유 한 줄**(노트 `리뷰:` 에). 기각은 정상 처분이다(경위 `references/rationale.md`).
   - **맞다고 확인된 지적은 전부 마감 전에 고친다** (2026-11-17 사용자 결정 — 넘기면 계속 밀리고 안 한 것이 남는다). 처분은 `반영`·`기각` 둘뿐이다 — 노트 §2·finding 큐·다음 milestone 으로 이월하지 않는다. 대조해서 틀린 지적만 기각한다. 마감 감사(4단계) 지적도 같다. `--fix` 자동 적용은 기본이 아니다.
   - 경계·소관 정본 `the-orchestration-repo/docs/adr/0033-closing-audit-seat.md`(자리 재획정) + `0031-three-verification-seats.md`(0015 가 안 바꾼 것).
3. **완료 노트** — 리뷰 반영 커밋과 스위트 재실행이 끝나 **HEAD 가 멈춘 뒤** 쓴다. 실행 중 적은 Ruling 이 있으면 §1 「결과」 끝에 `Ruling:` 목록으로 그대로 옮긴다(사용자가 여기서 뒤집는다 — 뒤집히면 그 step 은 재실행 대상). **이 스킬 디렉터리의 `templates/REPORT_TEMPLATE.md`**(스킬 로드 시 표시되는 Base directory 아래) 3섹션(결과 / 이슈와 해결 / 증거)으로 `archive/reports/<date>-<id>-<slug>.md`. **짧게** — 논거·경위는 changeset·커밋에 있다.
   - **§3 의 기계 사실은 손으로 쓰지 않는다** (2026-11-16 — 30일 감사 막는 지적 225건 중 141건이 노트 수기 오류였다). 커밋 범위·HEAD·커밋 수·트리 상태·스위트 기록·changeset 추적·완료 step `Files` 의 git 추적은 `python <이 스킬 Base directory>/bin/report_evidence.py --root "$HARNESS_ROOT" --base <milestone 시작 직전 커밋> --plan <계획서> --changeset <경로>… --write <노트>` 가 §3 표식 사이에 쓴다. exit 1 이면 블록의 경고(미커밋·스위트 미통과·추적 안 된 산출물)를 고치고 다시 돌린다. 커밋이 더 생기면 다시 돌린다 — `report_close` 가 블록 HEAD 를 현재 HEAD 와 대조해 거부한다.
   - 모델이 쓰는 §3 줄은 판단뿐이다: `검증:`(돌린 커맨드와 관측) · `실표면:` · `재현:`(레포 안 명령 — scratchpad 금지) · `리뷰:` · `감사:`(4단계 뒤) · 있으면 `구현됨·미검증:`·`스위트: waived — <사유>`·`수확:`(kg 후보 ≤2, 선택).
   - **노트를 쓰며 세 가지를 맞춘다** (2026-11-13 다섯 가지 중 트리·숫자는 블록이 맡는다):
     1. **게이트가 덮은 만큼만 주장한다** — 「전부 된다」고 쓰기 전에 그 게이트가 실제로 돈 입력(실물·fixture·일부·수동)을 본다. 6종 중 1종만 돌렸으면 1종이라고 쓴다. 돌리지 않은 검증은 `구현됨·미검증:` 에. 블록 밖에 적는 수치는 방금 본 출력만.
     2. **못 채운 DoD 는 잔여로 적는 것만으로 닫히지 않는다** — 계획서 진행 로그에 Ruling 으로 DoD 를 바꿨거나, 받을 milestone 의 ROADMAP 블록에 그 항목을 넣은 뒤에만 §2 에 적는다. 사용자 확인이 DoD 면 받은 원문이 있어야 충족이다. 계획의 결정·제약에서 벗어난 것도 Ruling 이 있어야 한다.
     3. **레포의 마감 기록을 채운다** — changeset README 의 Status·Result·Evidence 를 채우고 커밋한 뒤 블록을 생성한다. 레포에 `changesets/README.md` 인덱스가 있으면 그 행도 완료로.
4. **마감 감사 — `Agent(subagent_type="closing-auditor")`**(`model` 인자 없음). **노트가 쓰인 뒤·닫기 전**이 이 자리다 — 노트의 주장을 보려면 노트가 있어야 한다. **스폰 여부는 계획서가 정한다** (2026-11-16 사용자 결정): 계획서 `run 전 scope 결정` 의 `마감 감사:` 줄이 `함` 이면 스폰, `안 함` 이면 스폰하지 않고 `감사: none — 계획 결정`. 이 줄은 `/harness-plan` 승인 제시에서 사용자가 고른 값이다(연쇄 계획서는 아래 조건으로 끝난 세션이 적는다). 줄이 없는 옛 계획서만 조건으로 판정한다 — 장치 신설·개명 · 교차 레포 · `Risk: 위험` leaf ≥1 · 게이트/DoD 에 `평가 못 함` 중 하나라도 참이면 스폰(구 「step ≥3」은 거의 항상 참이라 폐지). 사용자가 「감사 생략」이라 하면 언제든 스폰하지 않고 `감사: none — 사용자 생략`.
   - 넘기는 것 5개: 소스 레포 경로(교차면 레포·범위 쌍 전부) · 커밋 범위 · 계획서 경로 · **완료 노트 경로** · 사용자 합격선 한 줄. 하나라도 빠지면 감사자가 그 축을 `미확인` 으로 돌려준다.
   - 축 5개(`완료`·`규약`·`정합`·`배선`·`교차`)와 각 축의 사정거리는 `the-orchestration-repo/docs/adr/0033-closing-audit-seat.md` §2 가 소유한다 — 여기 옮겨 적지 않는다.
   - **지적 처분은 2단계와 같다** — 대조 후 기각은 정상. 다만 `완료` 축의 막는 지적은 대개 **노트를 고쳐서** 닫는다(아직 `report_close` 전이라 수정이 정상 경로다). 반영으로 커밋이 생기면 스위트 → `report_evidence.py --write` 를 다시 돌린다.
   - 결과를 노트 §3 `감사:` 줄에 적는다. 안 돌렸으면 `감사: none — <계획 결정 | 조건 미해당 | 사용자 생략>`.
   - 이 milestone 이 명령·필드·파일·스킬을 은퇴시켰으면 `python "$HARNESS_SCRIPTS/../../harness-done/bin/retire_check.py" "<옛 이름>"…` 가 잔존 0 이어야 마감한다 — 잔존이 있으면 고치거나 남길 이유를 완료 노트에 적는다.
5. **닫기 + ROADMAP — 한 명령** (2026-11-16): `python <이 스킬 Base directory>/bin/close_milestone.py --root "$HARNESS_ROOT" --report <노트> --task-id <id> --milestone <ID> --summary "<사용자용 한 문장>" --plan <계획서>`. `report_close` → `roadmap_sync complete` → 계획서 `archive/plans/` 이동 → `repair-plan-pointers` → ROADMAP 이 150줄을 넘을 때만 `compact` 를 차례로 부르고, 실패하면 그 단계에서 멈춰 이름을 찍는다(고치고 같은 명령을 다시 — 끝난 단계는 건너뛴다). 그 뒤 스크립트가 끝에 찍은 `git add`·`git commit` 명령을 그대로 실행하고 push 한다 — 경로를 손으로 다시 적지 않는다(없는 옛 `plans/` 경로·gitignore 된 경로가 섞이면 add 가 통째로 실패한다). changeset 처럼 스크립트가 모르는 파일만 그 명령에 덧붙인다. 계획 승인 없이 마커가 `pending` 으로 남은 milestone(다른 레포 실전을 증거로 닫는 관측형 등)은 roadmap 단계가 거부한다 — 사용자가 마감을 승인했을 때만 `--force-roadmap` 을 더한다. 그런 milestone 은 애초에 따로 두지 말고 수리 milestone 의 DoD 로 넣는 편이 낫다(2026-11-19 M27).
   - `report_close` 가 거부하는 것: 빈 노트·`실표면:`/`재현:`/`감사:` 누락, 스위트 기록 없음·지문이 다른 코드의 기록(다른 커밋의 기록)·실패 상태(알려진 실패만이면 통과), §3 자동 블록 없음·다른 커밋 기준. 평가 못 한 검사는 `평가 못 함: <왜>` 로 표면화한다 — 통과가 아니다. ⚠ DoD 를 재실행하지 않는다 — 검증은 1단계와 `/harness-run` 이 한 것이다. 스위트 기록·자동 블록은 HEAD 만 대조하므로 미커밋 수정은 잡지 못한다.
6. **연쇄** — `python "$HARNESS_SCRIPTS/harness_work_state.py" next-chained --root "$HARNESS_ROOT" --json`. exit 1 = 목표 끝, 멈춘다. `unapproved_candidates` 는 초안이다 — 자동 승인 금지, `/harness-plan` 으로. exit 0(`ready` — 계획서·승인 이력 있음)·exit 3(`needs-plan` — 목표 chain 멤버인데 계획서 없음)이면 **이 세션이 다음 milestone 을 넘긴다**(2026-10-26 사용자 확정, ADR 0037). 목표 승인이 곧 실행 승인이다 — 사용자에게 묻지 않는다. 각 단계 결과를 한 줄씩 출력한다.
   1. **계획서**(exit 3 일 때) — 방금 닫은 milestone 의 완료 노트·Ruling·finding 큐와 출력된 DoD 를 재료로 `/harness-plan` §3~§4 규약대로 다음 계획서를 쓴다(인터뷰 없음). `## 의도 원문` 은 목표를 승인한 계획서의 것을 그대로 옮기고, milestone 절 `- **목표**:` 에 `chained-from <방금 닫은 work-id>`. 목표 범위 안에서 쪼개거나 합쳤으면 Ruling 으로 적는다. 계획서에서 사용자 몫(도메인·행동·취향·범위)인데 근거로 정할 수 없는 결정은 결정 로그에 `사용자 몫 미결` 로 적는다. 연쇄 계획서에는 plan-verifier 를 붙이지 않는다(2026-11-16 사용자 결정 — `## 검증자 지적 처분` 은 `none — 연쇄 계획`). `run 전 scope 결정` 의 `마감 감사:` 는 4단계 조건(장치 신설·개명 · 교차 레포 · `Risk: 위험` leaf ≥1)으로 `함`/`안 함` 을 적는다.
   2. **게이트** — `validate_plan_gate.py <plan> --pre-approval` PASS.
   3. **경계 결정** — 결정 로그에 `사용자 몫 미결` 이 남았으면 **모아서 한 번에** 묻고 멈춘다(AskUserQuestion 한 번). 답을 받으면 표식을 확정값으로 바꾸고 이어간다. milestone 안 실행 중 결정은 여기가 아니라 `/harness-run` 의 Ruling 소관이다.
   4. **승인** — `Status: approved (chain:<방금 닫은 work-id>)` 로 바꾸고 `approve_harness_plan.py <plan> --root "$HARNESS_ROOT" --work-id <새 id> --milestone-id <id> --changeset-path <path> --session-id <token> --chained-from <방금 닫은 work-id>` → ROADMAP 마커 `active` → `docs(plan): <제목> 계획 연쇄 승인` 단독 커밋·push. 거부(chain 밖·미결 남음)면 멈추고 보고.
   5. **넘기기** — 전달물 본문을 scratchpad 파일로 쓴다: 계획서 경로 · work-id · 이 세션이 닫은 milestone 의 완료 노트 경로와 Ruling · 목표 chain 의 남은 id · 첫 지시(「`/harness-run` 으로 이 계획을 실행한다. 착수 점검 → started → close-old 는 `/harness-run` 진입 절을 따른다」). 발사는 여기서 하지 않는다 — 6 의 `/session-end --relay` 가 HANDOFF 를 올린 뒤에 한다.
   6. **넘기고 마감** — 같은 턴에 `/session-end --relay`(약식 — 데이터 레포 push·HANDOFF 병합·커밋·push 뒤 발사, 2026-11-16·18)를 돌린다. 발사 명령으로 `python "$HARNESS_SCRIPTS/chain_handoff.py" launch --root "$HARNESS_ROOT" --work-id <새 id> --packet-file <파일> --model <계획서 실행 모델> --runtime <현재 런타임>` 을 넘긴다. 발사가 exit 0 이면 마지막에 `python "$HARNESS_SCRIPTS/chain_handoff.py" ended --root "$HARNESS_ROOT" --work-id <새 id>`. 이 탭은 새 세션이 닫는다 — 스스로 닫지 않는다. exit 4(재발사 후에도 착수 신호 없음)면 `ended` 를 기록하지 않고, 이 세션을 열어 둔 채 사용자에게 한 줄 보고하고 멈춘다(HANDOFF 는 이미 올라가 있다).
   - exit 0(`ready`)이면 1~3 을 건너뛰고 4(이미 승인돼 있으면 4 도 건너뜀)부터.
   - exit 1(목표 끝)이면 멈춘다. 약식 `--relay` 가 건너뛴 문서 위생·CLAUDE.md 점검은 이 세션이 끝날 때의 `/session-end` 끝내기 모드가 레포 전체로 한다.

**high-risk**(보안·결제·마이그레이션·대규모 diff·배포면)만 spec/quality 2축 + near-miss 기록으로 `ledger_append.py close` 경로를 탄다. 이 경로에는 스위트 대조가 없으니 `suite_gate.py` 결과를 직접 확인하고 닫는다.

**크기 회고 한 줄** — milestone 이 changeset 1개로 닫혔으면 그건 step 이었다. 노트에 적는다.

## 펼친 계획 — 갈래 마감과 메인 통합 마감 (2026-11-18 M26)

**갈래 마감** — 전달물 `.harness/fanout/branch.json` 이 있는 워크트리의 세션. 완료 경계 순서 1~4(DoD·스위트·코드 리뷰·완료 노트·계획서가 정했으면 감사)는 그대로 하고, 5·6 대신:
- 닫기 = `python <이 스킬 Base directory>/bin/close_milestone.py --root <갈래 워크트리> --report <노트> --task-id <갈래 work-id> --milestone <ID> --summary "<한 문장>" --branch`. `report_close` 만 돌고 ROADMAP·계획서 이동·compact 는 건너뛴다. 갈래 워크트리에서 `--branch` 없이 부르면, 전달물 없는 체크아웃에서 `--branch` 로 부르면 거부된다.
- 노트·계획서 체크박스를 커밋하고(`.harness/` 는 레포가 추적해도 커밋하지 않는다 — `harvest_worktree.py` 가 흡수를 거부한다) 갈래 브랜치를 push 한 뒤, 스크립트가 끝에 찍은 `fanout.py ready --root <갈래 워크트리> --note <노트>` 를 실행한다 — 완료 노트 실재·작업 트리 깨끗·push 됨을 확인하고 READY 를 쓴다(아니면 exit 1). 이것이 「병합 대기」 선언이고, 선언 뒤 갈래는 멈춘다. 병합·ROADMAP·HANDOFF 는 메인 몫이다. 연쇄(6)는 돌리지 않는다.
- 갈래를 접는 것은 그 탭에서 사용자가 `/harness-done drop` 을 명시할 때뿐이다 — 중단 노트·`report_close --drop` 까지만 하고 ROADMAP 은 건드리지 않는다. 메인에 알리려면 `fanout.py request --body "drop: <사유>"`.

**메인 통합 마감** — 등록부의 모든 갈래가 `absorbed`·`dropped` 일 때(`fanout.py status`). 메인 계획서의 통합 검증을 돌리고 완료 경계 순서 1~6 을 평소대로 한다. 완료 노트 §1 에 갈래마다 결과(병합 커밋·갈래 완료 노트 경로·dropped 사유)를 적는다 — 갈래 승인 영수증(`approved_by: fanout:…`)은 흡수 때 등록부 항목 `receipts` 로 옮겨져 있다. 병합으로 `plans/` 에 들어온 갈래 계획서는 같은 마감 커밋 전에 `git mv` 로 `archive/plans/` 에 옮긴다(갈래 마감은 계획서를 옮기지 않는다). 코드 리뷰 범위는 메인 milestone 시작 직전 커밋..HEAD(갈래 병합 포함)다.

## 중단 종결 — 외부 결과로 접을 때 (2026-11-03 M24)

공모전 미선발·외부 일정 취소처럼 **바깥 결과로 milestone 을 접는** 경로다. 완료 경계 순서(1~6)를 타지 않는다 — 완료가 아니므로 DoD 확인·코드 리뷰·마감 감사는 없고, 「완료」로 기록되면 안 된다. 계획서·work-id 가 없는 milestone(ROADMAP 에만 있던 것)도 같은 흐름이다.

진입: 사용자가 `/harness-done drop <id>` 를 치거나 「이 milestone 접자」·「M1 중단하자」처럼 중단을 **명시**할 때만. 모델이 실패·지연을 보고 스스로 중단을 판정해 접지 않는다.

1. **중단 노트** — 이 스킬 디렉터리의 `templates/DROP_TEMPLATE.md` 로 `archive/reports/<date>-<id>-중단.md`. 세 절(중단 사유 · 동결 산출물 · 재개 조건)과 `근거:` 줄(외부 결과의 출처). 미커밋 변경·워크트리·브랜치는 **경로만 적고 손대지 않는다** — 정리는 사용자 별도 지시.
2. **기록** — `python "$HARNESS_SCRIPTS/report_close.py" <노트> --task-id <work-id 또는 milestone-id> --root "$HARNESS_ROOT" --drop [--milestone-id <id>]`. ledger 에 `task_dropped` 한 건만 남고, work 가 있으면 status `dropped`, 없으면 ledger 기록만.
3. **ROADMAP** — `python "$HARNESS_SCRIPTS/roadmap_sync.py" drop --milestone <id> --evidence <노트> --reason "<한 줄>"` — 마커 `dropped` + 블록을 종결 섹션으로. 계획서가 있으면 `archive/plans/` 로 옮기고 `roadmap_sync.py repair-plan-pointers`.
4. **연쇄 후속** — `python "$HARNESS_SCRIPTS/harness_work_state.py" chain-remaining --root "$HARNESS_ROOT" --milestone-id <id>`. `remaining` 이 비어 있지 않으면 목록을 보여주고 **함께 접을 것을 사용자가 고른다**(AskUserQuestion 한 번, 복수 선택). 고른 것마다 1~3 을 같은 사유로 반복한다. 안 고른 것은 그대로 두되 **자동 연쇄(`next-chained`)를 돌리지 않는다** — 다음 착수는 사용자 지시로.
5. **커밋** — 노트·ROADMAP(·계획서 이동)을 `chore(roadmap): <id> dropped — <사유 한 줄>` 로 pathspec 커밋·push.

재개는 같은 id 로 되살리지 않는다 — 다시 하면 `/harness-plan` 으로 새 milestone 을 열고 중단 노트를 링크한다.

## ROADMAP 규칙

`ROADMAP.md` 는 milestone 상태만 관리하는 상위 장부(≤150줄)이고, 진행의 쓰기 정본은 계획서 체크박스다. 마커 형식(`harness:goal` 줄 + `harness:milestone` 블록의 `DoD`·`Evidence`·`Gap`·`Status`)은 번들 `init-ai-readiness.sh` 가 찍는 것이 정본이고 `session-end/bin/roadmap_parse.py` 가 읽는다 — 태그명·필드 키워드를 바꾸지 않는다.

- `DoD`·`Evidence` 없는 milestone 은 완료 처리하지 않는다. checkbox 만으로 완료 판단하지 않는다.
- `blocked`/`error` 는 완료 처리하지 않는다 — `- Blocked by:` 를 남기고 멈춘다.
- 150줄 초과 시 완료된 것부터 `docs/BACKLOG.md` 로 3~5줄 압축(`compact`). active/pending 은 자동 삭제 금지.
- 단일 컴포넌트·좁은 smoke 는 milestone 이 아니라 step 이다.

## Codex 에서

내장 `/code-review` 가 없어 2단계를 건너뛴다(노트에 `리뷰: none — Codex 런타임`). 4단계 마감 감사자는 `~/.codex/agents/closing_auditor.toml` 로 스폰된다 — 조건·축은 동일하다. Codex 쪽 정리는 2026-09-21 이후 별도 세션 소관.
