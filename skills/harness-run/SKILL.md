---
name: harness-run
description: >-
  하네스 흐름 2/3 — 실행. 승인 영수증이 등록된 계획서의 step 을 무개입으로 구현·검증·커밋한다(git 은 이 스킬이 소유). 진입은 사용자가 `/harness-run` 을 직접 치거나 `/harness-plan` 승인(ㄱㄱ)이 같은 턴에 넘기거나, 연쇄 넘기기 전달물(`.harness/handoff/<work-id>.md`)이 지시할 때뿐이다 — 하네스 진입점은 /harness-plan(사용자가 슬래시나 말로 이름을 부른다)이고 이 스킬은 그 연속 단계라 모델이 잇는다. "이어가"·"계속" 같은 자연어만으로 새로 켜지 않는다. 계획·승인이 아직이면 /harness-plan, milestone 완료 경계 마감은 /harness-done. 3종이 공유하는 기계장치 스크립트는 이 스킬의 scripts/ 가 보관한다.
---

# /harness-run — 무개입 실행 → 검증 → 커밋

> 3종 세트: `harness-plan` → **`harness-run`** → `harness-done`. 기계장치 경로·세션 초점:
> ```bash
> HARNESS_SCRIPTS="$HOME/.codex/skills/harness-run/scripts"
> [ -d "$HARNESS_SCRIPTS" ] || HARNESS_SCRIPTS="$HOME/.claude/skills/harness-run/scripts"
> HARNESS_ROOT="$(python "$HARNESS_SCRIPTS/harness_focus.py" resolve)"   # 초점 없으면 cwd
> ```
> 실행은 **오케스트레이터 모드**가 기본이다 — 부모는 계획 읽기·검증·커밋을 쥐고, 구현 leaf 는 `## 배차 설계` 의 worker 행대로 `implementer` 워커가 한다(wave 단위 병렬). 절이 없는 계획(동시 집합 1·판단 leaf)만 인라인. 혼자 도는 worker 행이 단독 배차 하한 아래면 직접 한다(아래 「착수 전 비용 자문」).

## 진입 — 승인 영수증

- `.harness/work.json`(checkout-local) 에 approval receipt(plan SHA-256)가 있고 현재 plan 과 일치해야 돈다. 없거나 어긋나면 `/harness-plan` 으로. 영수증은 **계획 본문의 무결성 씰**이지 승인 행위의 인증이 아니다.
- 승인은 실행할 바로 그 체크아웃(=`$HARNESS_ROOT`)에서 이뤄졌어야 한다. 워크트리라면 그 안에서 approve.
- **다른 세션이 연 work 이어받기**: `python "$HARNESS_SCRIPTS/harness_work_state.py" diagnose --root "$HARNESS_ROOT"` 로 상태·문서화된 정지 확인 → `... resume --root "$HARNESS_ROOT" --work-id <id> --session <runtime>:<uuid>`. 초점이 다른 레포면 먼저 `harness_focus.py set --root <소유 레포>`. 프롬프트 훅이 「현 세션 소유가 아닙니다」 한 줄을 붙이는 세션이 이 경우다. 선행 세션이 아직 살아 있거나 방금 커밋을 하나 더 만든 것은 정상 경로(발사 후 마감 중)이고 병렬 실행 신호가 아니다. work 식별은 발사 프롬프트의 `work=` 가 정본이고, 후보가 둘 이상이면 추론하지 말고 한 줄로 묻는다.
- **연쇄로 넘겨받은 세션** (ADR 0037 — 첫 프롬프트가 `.harness/handoff/<work-id>.md` 를 읽으라는 한 줄이면): 전달물을 읽고 **착수 점검** — ① 전달물의 계획서·work-id 가 실재 ② 기준선 확인(아래 「테스트 순서」 ①: 직전 증거 대조 또는 관련 검사) ③ `harness_work_state.py resume --root "$HARNESS_ROOT" --work-id <id> --session <runtime>:<uuid>`. **resume 이 성공하면 착수 신호(started)와 예전 탭 닫기(close-old 백그라운드 예약)를 스크립트가 알아서 한다** — 출력에 `연쇄 넘기기: started · close-old` 가 보이면 된다. resume 은 영수증이 계획서와 어긋나면 `started 보류` 를 출력하고 exit 1 — 그때도 막힘 절로. ①②가 실패하면 resume 을 부르지 말고 막힘 절로 — 예전 세션이 재발사·보고를 맡는다. ②는 「증거를 대조했거나 관련 검사를 실행했다」가 점검이지 「전체 초록」이 점검이 아니다 — 이미 빨간 기준선은 진행 로그에 적고 진행한다. close-old 가 ended 를 못 받으면(exit 5) 예전 탭은 닫히지 않고 `.harness/handoff/<id>.close-old.log` 에 남는다.
- 단일 step·가벼운 작업은 영수증 없이 진행하되 `/harness-plan` 의 "produce 끝 → run 진입" 한 줄을 거친 것이어야 한다.

## 실행

step 마다: **테스트 → 빨강 → 구현 → 초록 → 표면에 맞는 실구동 검증 → 커밋.** 웹=브라우저 · CLI=실행+exit code · API=실요청 · 데이터=1회 구동. lint/test 통과로 "됐다" 하지 않는다.

- **테스트 순서**: ① 세션 시작의 기준선은 **기존 실행 증거부터 확인**한다. 직전 완료된 pass의 명령·커밋·환경·입력과 현재 상태를 대조한다. 이후 소스·테스트·설정·의존성·원본 자산·미커밋 입력이 그대로임을 확인하면 그 기록을 시작 기준선으로 인용하고 재실행하지 않는다. 문서만 바뀐 경우도 이 대조를 기록한다. 달라졌거나 확인 못 한 부분은 관련 검사로 기준선을 잡고, 기존 전체 pass가 현재 전체를 보증한다고 쓰지 않는다. 증거가 없는 저장소는 관련 기존 검사부터 실행한다. 전체 검사가 착수 신호(resume/started)의 필수 선행 조건은 아니다. 이미 빨간 것은 진행 로그에 적고 내 몫이 아니면 건드리지 않는다. ② leaf 의 `Verify` 가 테스트면 **그 테스트부터 만들고 돌려 실패를 확인**한다(진행 로그 `- 빨강 step-N: <테스트> → <실패 한 줄>`). 구현 전에 통과하면 그 테스트는 이번 변경을 검사하지 못하는 것이니 단언을 고치고 다시 빨강을 본다. ③ 그다음 소스를 고쳐 초록. **테스트가 명세와 안 맞으면 테스트를 약하게 고치지 않고** Ruling 으로 적고 사용자 결정으로 올린다. ④ 버그 수정 leaf 는 재현 테스트가 ②다. ⑤ `Verify: 테스트 없음 — …` leaf 는 적힌 대신 확인 명령을 돌린다. ⑥ 커밋 전 변경 범위와 인접 회귀를 검사한다. **전체 스위트는 부모가 안정된 작업 묶음 또는 milestone 마감에서 1회** 실행하며 워커마다·leaf마다·세션을 넘길 때마다 중복 실행하지 않는다. 공용 기반 변경처럼 영향 범위를 좁힐 수 없으면 그 묶음에서 전체를 실행한다. 계획의 명시적 전체 검증 요구는 유지하고, 같은 입력의 완료 증거를 인용할 때는 재사용 근거를 남긴다. 시작 기준선 재사용은 마감 `suite_gate`의 현재 HEAD 검사를 면제하지 않는다.

- **장시간 검사 운용**: 실행 전에 범위·예상 시간·제한 시간을 정한다. 측정 이력이 없는 좁은 검사는 우선 300초 이내로 제한하고, 초과하면 실패/중단 증거와 마지막 테스트를 확인한 뒤 분할·프로파일링한다. 같은 전체 명령 재시작이나 제한 시간 증가는 원인 확인 없이 하지 않는다. 원본 전수 검증처럼 긴 검사는 측정 이력과 명시적 예산으로 실행한다. pytest는 `-vv --durations=20` 등 테스트 이름·소요시간을 남기고 실행 중 읽을 로그를 지정한다. 중단은 pass가 아니며, 시간 절약을 위해 단언·대상·원본 대조를 몰래 줄이지 않는다. 워커에는 관련 검사만 배정하고 전체 실행은 부모가 소유한다.

- **착수 전 비용 자문** (2026-11-18 M28): 일을 시작하기 전에 「이 비용을 들일 값이 있나」를 스스로 묻는다. 묻는 자리는 셋이다.
  - **오래 걸리는 제작**(촬영·빌드·판·대량 생성): 예상 소요가 15분을 넘으면 착수 전에 진행 로그에 `- 예상 소요 step-N: <무엇> 약 <분> — 대안 <더 싼 방법 | 없음>` 을 적는다. 더 싼 대안이 그 Artifact 의 판정 목적을 채우면 싼 쪽을 Ruling 으로 택해 계속한다(예: 전 영역 재촬영 대신 바뀐 영역만). 대안이 없으면 적은 대로 진행한다. 정지 사유가 아니다 — 묻는 상대는 자신이고, 택한 것은 Ruling 으로 사용자에게 보인다. 실제 소요가 예상의 두 배를 넘기면 같은 줄을 다시 적고 다시 묻는다.
  - **확인 차수**: 사용자 확인이 여러 번 도는 작업에서, 사용자가 말로 이미 정한 변경(문구 교체·삭제 등)은 반영하고 한 줄로 보고만 한다. 봐야 판정되는 변경(배치·색·크기)만 다시 찍어 보인다. 빌드는 한 차수의 변경을 다 모은 뒤 한 번 한다.
  - **혼자 도는 worker 행**: 같은 wave 에 함께 뜨는 워커가 없는 leaf 가 단독 배차 하한(메인이 대상 파일을 이미 읽었고 파일 2개 이내·10분 이내 — 자기 런타임의 서브에이전트 규약) 아래면 워커를 띄우지 않고 직접 하고, 진행 로그에 `- 인라인 step-N: 단독 배차 하한` 을 남긴다. 병렬 wave 의 워커는 크기와 무관하게 행대로 띄운다.

- **끊은 뒤 확인** (2026-11-18 M28): 백그라운드 명령을 끊었으면(TaskStop·프로세스 종료) 명령줄에 그 스크립트·명령 이름이 든 프로세스가 0 인지 확인한 뒤 다음 일을 한다 — 끊었다는 응답은 증거가 아니다. Windows: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*<이름>*' } | Select-Object ProcessId,CommandLine`. 남았으면 `Stop-Process -Id <pid>` 로 내리고 다시 0 을 본다. 여러 명령을 한 스크립트에 줄줄이 넣어 백그라운드로 돌리지 않는다 — 한 명령씩 띄워야 끊은 것이 끊긴다.

- step 을 끝낼 때마다 계획서의 `- [ ]`→`- [x]` 를 그 자리에서 켠다 — **체크박스가 진행의 쓰기 정본**. `.harness/work.json` 은 파생 포인터. **증거 없는 체크 금지** — 그 step 의 파일·커밋·검증 출력을 지금 인용할 수 있을 때만.
- 계획서의 scaffold 를 재해석하지 않는다. 범위가 바뀌면 재승인 대상.
- **무중단**: step 완료는 체크포인트이지 턴 종료 조건이 아니다. unchecked step 이 남아 있으면 다음 leaf 를 즉시 시작한다. **정지는 넷뿐** — ① 비가역·파괴 동작(삭제·덮어쓰기·리모트 파괴) ② 보안·시크릿이 걸리는 동작 ③ 워크트리 밖 부작용(머지·배포·외부 발송) ④ 사용자 명시 중단. blocked/error 는 「막힘」 절로.
- **실행 중 새 사용자 소유 결정이 나오면 멈추지 않는다 — Ruling 을 적고 진행한다** (사용자 결정). 계획서 `## 진행 로그`(append-only) 에 `- Ruling <n>: <결정> — 근거 <한 줄> — 되돌리기 <방법>` 를 적고 가장 보수적인(되돌리기 쉬운) 쪽을 택해 계속한다. 정지 4종에 걸리는 결정만 평문 질문으로 멈춘다. **승인된 결정을 실행 중에 뒤집는 것도 Ruling 이다**(`- Ruling n: D3 정정 — …`) — 결정 로그는 승인 후 불변이므로 번복은 진행 로그에만 산다. 턴 종료 보고와 `/harness-done` 완료 노트에 Ruling 목록을 그대로 올려 사용자가 뒤집을 수 있게 한다.
- **초반 점검 한 번** — leaf 가 4개 이상인 계획은 **둘째 leaf 를 켠 직후** 멈추지 않고 한 번 본다(긴 실행의 실패는 처음 몇 단계에서 시작해 되돌릴 수 없을 때까지 드러나지 않는다 — 근거 a-o `research/2026-11-13-the-orchestration-repo-multi-agent-workflow.md`). ① 계획서 `## 의도 원문`·결정 로그를 다시 읽고 지금까지의 변경(`git diff --stat <실행 시작 커밋>..HEAD`)이 그 방향인가 ② 남은 leaf 가 기대는 전제(앞 leaf 가 만든 파일 경로·형식·인터페이스)가 실제 산출물과 같은가 ③ 지금까지 적은 Ruling 이 남은 leaf 를 바꾸는가. 진행 로그에 `- 초반 점검: 방향 맞음` 또는 `- 초반 점검: 어긋남 — <무엇>` 한 줄을 적는다. 어긋나면 남은 leaf 를 그대로 밀지 않는다 — Ruling 으로 남은 leaf 를 고쳐 계속하거나(범위가 바뀌면 재승인 대상) 「막힘」으로 올린다.
- milestone DoD 가 충족되는 완료 경계에 닿으면 멈추지 말고 `/harness-done` 을 로드한다.

## 배차 — wave 단위 병렬 (계획에 `## 배차 설계` 절이 있을 때)

절의 행대로 워커를 스폰한다. 절차 정본 `references/fanout.md`. 순차 leaf 도 워커 행이면 그 모델로. **체크박스는 오케스트레이터만 켠다** — 워커 보고는 재료이고 leaf Verify 를 부모가 직접 재실행한 뒤에만.

- **Claude 표면**: 현재 wave 의 worker 행을 **한 응답에서 동시에** `Agent(subagent_type="implementer")`(background) 로 스폰한다 — 행이 `worker(sonnet)` 이면 인자 없이, 다른 모델이나 effort 가 적혀 있으면 `model`·`effort` 인자로 그 값을 준다. `researcher` 행은 `Agent(subagent_type="researcher")` 를 `--review-first` 로 함께 띄운다. **Codex 표면**: `spawn_agent(agent_type="implementer")` 를 같은 식으로 병렬(모델은 정의 값).
- 워커 프롬프트 = 그 leaf 본문(Artifact·Files·Verify·Failure probe) + 정본 경로 + **「커밋 금지」**. 보고 형식은 정의가 소유하니 되풀이하지 않는다. 대화 전체는 넘기지 않는다. 워커 보고의 `verification` 줄에 **빨강 출력과 초록 출력이 둘 다** 있어야 재실행으로 넘어간다 — 빨강이 없으면 되돌려 보낸다.
- 취합: 워커 보고 → 부모가 leaf `Verify` 재실행 → **그 leaf 의 파일만 pathspec 커밋** → 체크박스. 다음 wave 는 앞 wave 의 leaf 가 전부 켜진 뒤.
- **빨강 줄이 없으면 체크박스를 켜지 않는다**. `Verify` 가 테스트인 leaf 는 inline 이든 워커든 **진행 로그에 `- 빨강 step-N: <테스트> → <실패 한 줄>` 이 먼저 있어야** `- [x]` 로 바꾼다. 「완료(해시)」 한 줄은 빨강 줄을 대신하지 못한다. 소스를 먼저 고쳤으면 `- 빨강(사후) step-N: …` 으로 순서를 그대로 적는다 — 되돌려 보내지는 않지만 그 테스트는 부모가 더 의심해서 본다.
- 같은 레포 동시 스폰이 허용되는 근거는 커밋 주체가 부모 하나라는 것(`context/delegation.md`). 파일이 겹치는 leaf 는 워크트리로 격리하지 않고 순차로 돌린다 — 워크트리는 사용자와 대화하는 갈래(아래 절)에만 쓴다.

## 펼친 계획 — 메인 통합자와 갈래 (계획에 `## 갈래 목록` 절이 있을 때, 2026-11-18 M26)

장치는 `"$HARNESS_SCRIPTS/fanout.py"`(하위명령 `open`·`status`·`wait`·`mark`·`ready`·`request`). 표식은 파일이라 메인 세션이 닫혀도 새 세션이 `fanout.py status` 로 이어받는다.

**메인 = 통합자** — 실시간 감독자가 아니다. 갈래 화면을 읽거나 끼어들지 않고 표식 파일만 기다린다.
1. **펼치기** — `## 갈래 목록` 행을 JSON 배열(`[{"id","title","dod","owns":[…]}]`)로 scratchpad 에 쓰고 `python "$HARNESS_SCRIPTS/fanout.py" open --root "$HARNESS_ROOT" --main-work-id <work-id> --milestone-id <milestone> --base-branch <브랜치> --branches-json <파일> --model <계획서 실행 모델>`. 갈래마다 워크트리·전달물(`.harness/fanout/branch.json`)·세션이 생기고 등록부 `.harness/fanout/<work-id>.json` 에 `running` 으로 남는다. exit 1 = 일부 갈래 실패(그 워크트리는 정리됨) — 실패 갈래를 다시 `open` 하거나 진행 로그에 Ruling 으로.
2. **기다리기** — `python "$HARNESS_SCRIPTS/fanout.py" wait --root "$HARNESS_ROOT" --main-work-id <work-id> --timeout <초> --interval <초>` 를 백그라운드로 건다. 시도마다 한 줄을 찍고 상한에서 exit 2. 새 표식이 있으면 `READY <갈래>` 또는 `REQUEST <갈래> <파일>` 을 찍고 exit 0.
3. **표식 처리 → 다시 2**
   - `REQUEST` = 계약 변경 요청 — 메인 계획서 `## 갈래 목록` 의 소유 표를 고치는 것은 메인만 한다— 진행 로그에 `- 계약 변경 <n>: <갈래> <무엇> (REQUEST-<n>)` 을 적고 표를 고친 뒤, 승인 해시가 본문을 봉인하므로 같은 `--fanout` 목록으로 `approve_harness_plan.py` 를 다시 돌려 영수증을 묶는다(소유 표 변경은 메인 계획 승인 때 사용자가 메인에 맡긴 권한이다). 처리하면 같은 폴더에 `REQUEST-<n>.done` 을 쓴다. 갈래 사이 설계 충돌이 보이면 멈춰 사용자에게 묻는다.
   - `READY` = 병합 대기 — 「병합 대기」 선언이 곧 사용자 확인이다. `python "$HARNESS_SCRIPTS/harvest_worktree.py" --root "$HARNESS_ROOT" --branch <갈래 브랜치>`(dry-run) 출력을 진행 로그에 남기고 `--apply`. 등록부 갈래는 READY 표식이 없으면 거부된다. 병합·워크트리 제거 뒤 등록부가 `absorbed`. 갈래 탭이 남아 있으면 `--close-tabs` 를 붙인다 — 탭을 닫고 명령줄에 그 워크트리 경로가 든 남은 프로세스(dev 서버 등)를 종료한 뒤 폴더를 지운다(dry-run 이 목록을 먼저 보여 준다). 병합 충돌이면 멈춰 묻는다.
   - 갈래 탭에서 사용자가 drop 을 명시했으면 `fanout.py mark --branch-id <id> --state dropped` 뒤 `harvest_worktree.py` 로 병합 없이 정리만 한다. 통합은 남은 갈래로 계속한다.
4. 모든 갈래가 `absorbed`·`dropped` 이면 통합 검증 → `/harness-done` 메인 통합 마감.

**갈래 세션 규칙** — 전달물 `.harness/fanout/branch.json` 이 있는 워크트리의 세션.
- 자기 계획서·영수증은 `/harness-plan` 갈래 절차(`--fanned-from`)로 만든다. 실행은 이 스킬 그대로.
- **상태 파일을 쓰지 않는다** — `ROADMAP.md`·`docs/BACKLOG.md`·`HANDOFF.md` 는 메인 소유.
- **step 착수마다 `git fetch` 후 base 브랜치로 rebase** — 메인이 고친 계약·흡수된 다른 갈래를 받는다.
- 소유(`owns`) 밖을 바꿔야 하면 `python "$HARNESS_SCRIPTS/fanout.py" request --root <갈래 워크트리> --body "<무엇을 왜>"` 를 남기고 무관한 일을 계속한다. 사용자 몫 결정은 이 탭에서 묻는다.
- 끝은 `/harness-done` 갈래 마감(리뷰·완료 노트·`close_milestone.py --branch`·push·`fanout.py ready`)이다. 병합은 메인이 한다.

## 막힘

**멈춤 = 판단 불능**(아키텍처 불일치 · 스펙 위반 의심 · 모호 · 해결 불가 충돌 · 취향). 되돌릴 수 없음은 멈춤 사유가 아니다 — 계획서 `Risk` 가 정한 격리·검증으로 처리한다. 파괴 행위는 guard 가 그냥 막는다.

0. **가진 것을 먼저 꺼낸다** — `askda recall "<막힌 지점 한 줄>"` 한 번(6축, `/data`). 히트가 있으면 그것으로 1 을 시도한다.
1. **빠진 컨텍스트를 주입해 재시도** — 계획서·spec·이전 결정에서 놓친 것을 찾아 같은 leaf 재시도. 필요하면 조사만 서브에이전트에 맡긴다(서브에이전트는 사용자에게 직접 묻지 않는다).
2. **평문 질문 한 문장으로 정지** — 사용자가 읽을 한 문장(경로·내부 ID 없이)으로 묻고 턴을 마친다. 알림 장치는 없다.

## 커밋·푸시

- **커밋과 origin push 는 완료 절차의 일부다** — "푸시할까요?"로 정지하지 않는다. 예외만 정지: force-push 등 리모트 파괴 · 신규 공개 리포·가시성 변경 · 사용자가 "커밋만/푸시 보류" 명시.
- **공유 레포(여러 세션이 함께 쓰는 레포)에서는 `git add -A` 금지** — 이번 작업이 바꾼 경로만 나열해 add. 커밋 직전 `git status --short` 로 남의 변경이 섞이지 않았는지 본다.
- 워크트리에서는 커밋 전 `python "$HARNESS_SCRIPTS/check_worktree_scope.py" --root "$HARNESS_ROOT"` — exit 1 이면 메인 소유 파일(`ROADMAP.md`·`changesets/README.md`·`docs/BACKLOG.md`)을 쓰고 있다는 뜻이고 그건 거두는 메인 세션이 쓴다.

## 턴 종료 보고

멀티스텝 작업 중 턴을 마칠 때(정지·질문 어느 경우든) 최종 메시지 끝에 **계획 위치 2줄** — `Milestone <id> <제목> (완료 x/y)` · `다음: <step-N>`. Ruling 이 있으면 그 아래 `Ruling: n건 — <각 한 줄>`. 모델이 직접 쓴다. 단일 step 작업은 생략.

## 재개·에러

문서화된 정지의 재개 = blocker 가 실제 해소됐는지 근거 확인(기계가 대신 못 한다) + `harness_work_state.py resume`. error 는 status 를 `pending` 으로 되돌리고 메시지 삭제 후 재실행.

## Codex 에서

같은 절차. Codex 쪽 정리는 2026-09-21 이후 별도 세션 소관.
