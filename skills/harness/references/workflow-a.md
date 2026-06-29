> harness 갈래 본문 (lazy-split, F2). SKILL.md(§0~§B3 공통)를 먼저 읽은 뒤 §0 에서 이 갈래로 판정됐을 때 읽는다. §A1/§B2-scope/§B3 등 상호참조는 SKILL.md 에 있다.

## ▶ WORKFLOW-A — playbook 작성 (1회성)

### §C-workflow-A. Step 설계

**1 playbook 신규 작성 = 1 step**. 4섹션(입력 / 절차 / 체크리스트 / 근거★) 채우기.

설계 원칙:
- 각 절차 단계는 결정론적 vs 판단 필요 구분
- 체크리스트는 *측정 가능* (날짜 확인 / 도구 cross-check 등)
- 근거 섹션 비면 commit 차단 (judge 강제)

### §D-workflow-A. 파일 생성

```bash
cp playbooks/PLAYBOOK_TEMPLATE.md playbooks/<task-slug>.md
```

4섹션을 채워라. 근거 섹션엔 `docs/DOMAIN.md` 의 표 또는 `config/sources.md` 의 도구를 인용.

인덱스 표 갱신:
```markdown
# playbooks/README.md
| # | 슬러그 | 도메인 | 마지막 적용 | 적용 횟수 |
|---|--------|--------|------------|----------|
| 3 | vat-quarterly | VAT 분기 신고 | - | 0 |
```

### §E-workflow-A. 실행

> **게이트**: §B2 적용 — 기본 통과(한 줄 통지 후 진입), "계획부터 보여줘" 류 요청 시만 §E 전 정지. (정책 본문은 §B2 단일 출처)

#### ★ E-1. 섹션 채울 때마다 진행 표시
**트리거는 시간이 아니라 섹션 전이다.** 4섹션 중 한 섹션을 채울 때마다 진행 메모를 갱신 (예: 임시 commit 또는 인덱스 표 noted 컬럼).

#### E-2. Judge 규약 — 외부 권위 인용 강제
근거 섹션의 모든 항목은 **법조문 URL · 기준 고시 번호 · 공식 도구 호출 로그** 중 하나를 포함. 모델 self-judgment 으로 추정 작성 금지 (M4 V3 self-eval 천장 회피).

#### E-3. 도메인 cross-check
`docs/DOMAIN.md` 의 기준일 / 정의가 playbook 의 가정과 일치하는지 검증 후 진행.

#### E-4. commit 단위
1 playbook = 1 commit:
```bash
git commit -m "playbook: vat-quarterly (4/4 + 근거 3건)"
```

#### E-5. ROADMAP milestone sync
새 playbook 작성이 `ROADMAP.md` milestone DoD 를 닫으면 §B3 helper 로 milestone 을 완료 처리한다. 근거 섹션이 비어 있거나 도메인 cross-check 가 끝나지 않았으면 완료 처리 금지.

---
