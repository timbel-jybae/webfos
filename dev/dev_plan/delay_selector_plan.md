# 검수자 지연시간 선택 기능 개발 계획서

## 1. 개요

### 1.1 목적
검수자가 지연시간을 직접 선택할 수 있도록 UI 개선

### 1.2 현재 상태
- `useDelayBuffer.js`에서 `TARGET_DELAY_SECONDS = 3.5` 고정
- UI에서 용어 혼란: `bufferHealth`를 "지연"으로 표시 중

---

## 2. 개발 단계

### Phase 1: UI 용어 수정
- [ ] `DelayedPlayer/index.jsx` 수정
  - "지연" → "버퍼" (bufferHealth)
  - 실제 지연 설정값 표시 추가

### Phase 2: DelaySelector 컴포넌트 생성
- [ ] `components/DelaySelector/index.jsx` 생성
  - QualitySelector와 유사한 구조
  - 옵션: 2초, 3초, 4초, 5초
- [ ] `components/DelaySelector/styles.css` 생성

### Phase 3: useDelayBuffer 수정
- [ ] `TARGET_DELAY_SECONDS`를 외부 파라미터로 변경
- [ ] `startBuffer(videoTrack, audioTrack, quality, delaySeconds)` 시그니처 변경
- [ ] 지연시간 변경 시 버퍼 재설정 로직

### Phase 4: App.jsx 통합
- [ ] `selectedDelay` 상태 추가
- [ ] `DelaySelector` 렌더링
- [ ] `DelayedPlayer`에 delay prop 전달

### Phase 5: DelayedPlayer 수정
- [ ] delay prop 수신
- [ ] 지연시간 변경 시 버퍼 재시작
- [ ] 현재 지연 설정값 표시

---

## 3. 상세 설계

### 3.1 DelaySelector 컴포넌트

```jsx
/**
 * 지연시간 선택 컴포넌트
 * 
 * @param {number} value - 현재 선택된 지연시간 (초)
 * @param {function} onChange - 변경 콜백
 */
function DelaySelector({ value, onChange }) {
  // 옵션: 2, 3, 4, 5초
}
```

### 3.2 useDelayBuffer 변경

```javascript
// 기존
const TARGET_DELAY_SECONDS = 3.5

// 변경
function startBufferGlobal(videoTrack, audioTrack, quality, videoElement, delaySeconds = 3.5) {
  globalState.targetDelay = delaySeconds
  // ...
}
```

### 3.3 UI 표시 예시

```
┌───────────────────────────────────────┐
│  화질: [720p ▼]  지연: [3초 ▼]        │
│  ┌───────────────────────────────────┐│
│  │                                   ││
│  │         지연 영상 화면             ││
│  │                                   ││
│  └───────────────────────────────────┘│
│  처리: 150 | 버퍼: 3.2s | 지연: 3.0s  │
└───────────────────────────────────────┘
```

---

## 4. 체크리스트

- [x] Phase 1: UI 용어 수정
- [x] Phase 2: DelaySelector 컴포넌트 생성
- [x] Phase 3: useDelayBuffer 수정
- [x] Phase 4: App.jsx 통합
- [x] Phase 5: DelayedPlayer 수정
- [ ] 테스트: 지연시간 변경 동작 확인

---

## 5. 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 0.1.0 | 2026-02-26 | 초기 계획서 작성 |
| 1.0.0 | 2026-02-26 | 구현 완료 |
