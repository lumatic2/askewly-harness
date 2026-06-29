> harness 갈래 본문 (lazy-split, F2). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤 §0 에서 이 갈래로 판정됐을 때 읽는다. §A1/§B2-scope/§B3 등 상호참조는 SKILL.md 에 있다.

## ▶ PRODUCT — phases/ 패러다임 (jha0313)

### §C-product. Step 설계 (= 분해 트리의 leaf spec 엔진)

> **이 단계의 역할**: §B2-scope 의 재귀 분해가 milestone→step 트리를 펼치면, §C 는 각 leaf step 을 *실행가능 spec*(읽을 파일·시그니처 작업·AC)으로 완성한다. 긴 작업이면 트리 전체(여러 stepN.md)를 §E 실행 *전에* 펼쳐 plan doc 과 함께 박는다 — 새 에이전트가 그걸로 몇 시간 돈다.

> **선행 게이트**: 이 단계 전에 §B0(Spec readiness)이 PASS 해야 한다. `docs/PRD.md`·`docs/ARCHITECTURE.md` 가 비어 있거나 백엔드·인증·디자인·스코프 같은 사용자 소유 결정이 미해결이면, step 을 쪼개기 전에 §B0 으로 돌아가 합의·기록부터 끝낸다. 빈 spec 위에서 step 을 설계하면 추정으로 잘못된 결과물이 나온다.

#### 설계 원칙 (jha0313 7원칙)

1. **Scope 최소화** — 한 step 에 한 레이어/모듈
2. **자기완결성** — 외부 참조 금지, 필요 정보 전부 step 파일 안에
3. **사전 준비 강제** — 관련 문서 경로 + 이전 step 생성 파일 명시. 각 경로에 *왜 필요한지* 한 줄(D-3 템플릿 참조 — feedforward)
4. **시그니처 수준 지시** — 인터페이스만, 내부는 에이전트 재량. 핵심 규칙(멱등성·보안)은 명시
5. **AC 는 실행 커맨드** — `npm run build && npm test` 같은 실행 가능한 검증
6. **주의사항은 구체적으로** — "X 하지 마라. 이유: Y" 형식
7. **네이밍** — kebab-case slug (`auth-flow`, `api-layer`)

### §D-product. 파일 생성

#### D-1. `phases/index.json` (top-level)
```json
{ "phases": [ { "dir": "0-mvp", "status": "pending" } ] }
```

#### D-2. `phases/<task>/index.json` (task 상세)
```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "mode": "product",
  "steps": [ { "step": 0, "name": "project-setup", "status": "pending" } ]
}
```

상태 전이 시 추가 필드 (Claude 가 status 변경할 때 함께 기록):

| 전이 | 추가 필드 |
|------|---------|
| → `completed` | `summary` (한 줄), `completed_at` (KST ISO) |
| → `error` | `error_message`, `failed_at` |
| → `blocked` | `blocked_reason`, `blocked_at` |

`summary` 는 다음 step preamble 컨텍스트로 전달 — 다음에 유용한 정보(생성 파일·핵심 결정)를 담아라.

#### D-3. `phases/<task>/step{N}.md`
```markdown
# Step {N}: {이름}

## 읽어야 할 파일
> 각 항목에 **왜**(이 step 에 어떻게 쓰이나)를 붙여라 — 경로만 주면 에이전트가 전부 읽고 관련성을 추측한다. 이유가 있으면 우선순위를 안다. (Trellis `implement.jsonl` 의 `{file, reason}` 축소판 — 정의 v2.6 feedforward 축, Accepted)
- docs/ARCHITECTURE.md — 왜: {이 step 의 모듈 경계·인터페이스가 여기 정의됨}
- docs/adr/{n}-{title}.md — 왜: {이 step 이 구현하는 결정}
- {이전 step 생성/수정 파일} — 왜: {이어받는 상태·계약}

## 작업
{시그니처 수준 지시 + 핵심 규칙 박제}

## Acceptance Criteria
\`\`\`bash
npm run build && npm test
\`\`\`

## 검증 절차
1. AC 커맨드 실행
2. ARCHITECTURE 구조 / ADR 기술 스택 / CLAUDE.md CRITICAL 위반 여부
3. `phases/<task>/index.json` step 업데이트:
   - 성공 → `completed` + `summary`
   - 3회 실패 → `error` + `error_message`
   - 사용자 개입 필요 → `blocked` + `blocked_reason` + 즉시 중단

## 금지사항
- {X 하지 마라. 이유: Y}
- 기존 테스트 깨지 마라
```

### §E-product. 실행

> **게이트**: §B2 적용 — 기본 통과(한 줄 통지 후 진입), "계획부터 보여줘" 류 요청 시만 §E 전 정지. (정책 본문은 §B2 단일 출처)

#### ★ E-1. step 전이마다 status 갱신
**트리거는 시간이 아니라 전이 이벤트다.** step 이 `pending → in_progress → completed/error/blocked` 로 바뀌는 *그 시점*에 `phases/<task>/index.json` 을 갱신. 한 step 이 길면 의미 있는 하위작업 경계(파일 생성·AC 커맨드 실행 직후)에서도 갱신해 사용자가 중단 시 어디까지 됐는지 복원 가능하게. 작업 끝났는데 status 안 바꾼 상태로 보고 금지.

#### E-2. 가드레일 자동 주입
매 step 시작 시 CLAUDE.md + ARCHITECTURE·ADR·(web=루트 `DESIGN.md` / mobile=`docs/UI_GUIDE.md`) 읽기. § Judge 규약 위반은 step 시작 전 거부.

#### E-3. 컨텍스트 누적
이전 완료 step `summary`(§D-2 형식 — 생성 파일·핵심 결정·검증 결과)를 다음 step 에 전달. **"한 줄"이 아니라 *다음 step 이 이전 산출물을 다시 안 읽어도 되는* 만큼 두껍게.** 단 noise 는 빼라(필요한 것만 — feedforward 우선순위 Correctness>Completeness>Size).
> 근거(dogfooding 2026-06-11): 실사용 summary 는 전부 밀도 높은 단락(파일경로·테스트수·결정)이고 그래서 re-read/re-ask 신호가 ~0. "한 줄"을 곧이곧대로 지키면 thin-context 가 터진다. + 운영자가 *아는 도메인 지뢰*(예: "주택 양도=§94①1호, 주식 아님")는 다음 step 산출 전에 그 step 의 `## 금지사항`/주의에 박아라 — verify 가 사후에 잡기 전에 예방(income calc3 전례: 사전주입 부재로 오분류→verify.ok=false→교정, late catch).

#### E-4. 자가 교정 (3회 retry)
실패 시 *직전 에러 메시지* 를 다음 시도 컨텍스트에 박고 재시도. 3회 후 `error`.

#### E-5. 2-phase commit
```bash
git commit -m "feat(<phase>): step N — <name>"   # 코드 변경
git commit -m "chore(<phase>): step N output"     # index.json + step output
```

#### E-6. blocked 처리
API 키·외부 인증·사용자 의사결정 필요 시 즉시 `blocked` + 사유 기록 + 멈춤. 추정 진행 금지.

#### E-7. ROADMAP milestone sync
phase 전체 또는 이 step 이 `ROADMAP.md` 의 milestone DoD 를 닫는 경우에만 §B3 helper 를 실행한다. step 완료와 milestone 완료를 혼동하지 않는다. milestone 이 닫히면 `complete` → `compact` → `horizon-check` 순서로 처리하고, horizon 이 비었으면 기본적으로 gap report 생성 후 멈춘다. 단 사용자가 명시적으로 continuation 을 요청한 경우에만 §B3 `Continuation opt-in` gate 로 다음 후보 승격 여부를 판단한다.

---
