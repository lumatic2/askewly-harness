# {NNN} — {milestone-id} {slug}

> 짧게 쓴다. 경위·설계 논거·회고는 **커밋 메시지**에. evidence 문서가 상세를 가지면 여기는 경로 + 한 줄 — **재서술 금지**.
> milestone 당 이 파일 1개(기록-합본) — step 은 아래 절로 쌓는다. 단발 maintenance 는 step 절 1개짜리로 쓴다.

- Date: {YYYY-MM-DD}
- Milestone: {ID · plan 경로}
- Status: in_progress

## Scope
- Files: {step 진행에 따라 누적}
- 되돌리기: {revert 방법 · 배포본이 있으면 setup.sh 재실행 · 삭제한 것이 있으면 복원 위치}

## step-1: {제목}
- Goal: {한 줄}
- Probe: {반드시 실패해야 하는 것 1건 → 결과}
- Verification: [ ] targeted tests [ ] smoke [ ] sync/deploy 대조(해당 시)
- Result: {핵심 관측 1줄 · evidence 경로}
  <!-- 배차했으면 여기(또는 Goal)에 `위임: <모델> 워커` 와 **오케스트레이터 재확인 한 줄**(표본 재실행·실물 대조)을 남긴다 — 커밋 가드가 확인한다 (DC2) -->
  <!-- 검증에서 나온 non-blocking 지적은 `- 권고: <내용> → 수정함` 또는 `— 받아들이고 안 함, <이유>` 로 같은 줄에 처분한다 — 커밋 가드가 확인한다 (DC3) -->

## Result (milestone 통합)
- Status: pending
- Evidence: {통합 검증 1줄 — pytest/doctor/게이트}
