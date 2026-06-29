# 모바일 UI 가이드 (RN / Flutter / 네이티브)

## 디자인 원칙
1. {예: "OS 네이티브 컴포넌트 우선. 커스텀은 차별화 가치 있을 때만."}
2. {원칙 2 — 예: 한 손 사용 가정, 주요 액션은 하단}
3. {원칙 3}

## 모바일 AI 슬롭 안티패턴 — 하지 마라

| 금지 사항 | 이유 |
|-----------|------|
| 터치 타겟 < 44pt (iOS) / 48dp (Android) | 손가락이 못 찍음. Apple HIG / Material 공통 최소치 |
| `SafeArea` / `safe-area-inset` 무시 | 노치·홈인디케이터 영역에 콘텐츠 묻힘 |
| 시스템 다크모드 미대응 | `prefers-color-scheme` / `useColorScheme()` 안 보고 라이트만 박제 |
| 풀스크린 모달 남발 | 사소한 액션도 시트/팝업이면 될 걸 push 로 stack 쌓음 |
| 키보드가 입력 필드 가림 | `KeyboardAvoidingView` / `resizeToAvoidBottomInset` 누락 |
| 햅틱 0회 | 중요 액션(삭제·완료·결제)에 햅틱 없으면 모바일 같지 않음 |
| 모든 화면 동일한 `rounded-3xl` 카드 | 웹 슬롭 그대로 들고옴. iOS/Android 네이티브는 더 절제됨 |
| 가로 스크롤 + 세로 스크롤 중첩 | 스크롤 충돌. 한 방향만 |

## 플랫폼 차이 (iOS / Android)
- 뒤로가기: iOS 좌상단 chevron + edge swipe / Android 시스템 back + AppBar back
- 탭바: iOS 하단 / Android 상단 또는 하단 (Material 3 NavigationBar)
- 시트: iOS detents (medium/large) / Android Bottom Sheet
- 폰트: iOS SF / Android Roboto — 시스템 스택 권장 ({tech stack 채울 것})

## 색상 토큰 (light/dark 쌍)
| 용도 | Light | Dark |
|------|-------|------|
| 배경 | {예: #FFFFFF} | {예: #000000 (iOS true black)} |
| 카드 | {예: #F2F2F7 (iOS gray6)} | {예: #1C1C1E} |
| 텍스트 주 | {예: #000000} | {예: #FFFFFF} |
| 텍스트 보조 | {예: #3C3C43 99%} | {예: #EBEBF5 60%} |

## 타이포그래피 (Dynamic Type / fontScale 반응)
- 폰트 크기는 *고정 px 금지*. `useDynamicValue` / `MediaQuery.textScaleFactor` 반영
- 헤딩: {SF Pro Display / Roboto Bold, 28-34}
- 본문: {SF Pro Text / Roboto Regular, 17 iOS / 16 Android}

## 간격·터치 영역
- 터치 타겟 최소: 44×44 pt (iOS) / 48×48 dp (Android)
- spacing scale: {4·8·12·16·24·32}
- 카드 padding: 최소 16

## 접근성
- `accessibilityLabel` / `semanticsLabel` 필수 — 아이콘만 있는 버튼에 특히
- 대비비 WCAG AA: 4.5:1 (본문) / 3:1 (큰 텍스트)
- VoiceOver / TalkBack 으로 한 번 통과 시켜보기
