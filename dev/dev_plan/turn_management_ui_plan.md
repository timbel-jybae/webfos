# 턴 관리 UI 및 연동 개발 계획서

## 1. 개요

### 1.1 목적
속기사 턴 관리 기능을 프론트엔드 UI와 백엔드 RoomAgent/TurnManager에 연동하여, 
송출 권한 기반의 자막 작업 흐름을 구현한다.

### 1.2 요구사항
1. 속기사 패널 헤더에 참가자 UUID 표시
2. 먼저 입장한 속기사가 '송출 권한' 획득
3. 각 참여자는 본인 입력란에만 텍스트 입력 가능
4. '송출 권한'을 가진 사람만 송출 가능
5. 송출된 텍스트는 '송출 텍스트'에 표시
6. 1회 송출 후 송출 권한이 다음 속기사로 이동
7. 현재 송출 권한자의 입력창에 권한 표시

---

## 2. 개발 단계

### Phase 1: 프론트엔드 상태 관리

- [ ] `useLiveKit.js` 수정
  - localParticipant identity 반환 추가
  - 참가자 목록에서 속기사 필터링

- [ ] `App.jsx` 상태 추가
  ```javascript
  const [myIdentity, setMyIdentity] = useState(null)
  const [stenographers, setStenographers] = useState([])  // [{ identity, text }]
  const [currentTurnHolder, setCurrentTurnHolder] = useState(null)
  const [broadcastText, setBroadcastText] = useState('')
  ```

### Phase 2: StenographerPanel 기능 확장

- [ ] Props 확장
  - `identity`: 참가자 UUID
  - `isMyPanel`: 본인 패널 여부
  - `hasTurn`: 송출 권한 보유 여부
  - `onTextChange`: 텍스트 변경 콜백
  - `onBroadcast`: 송출 버튼 클릭 콜백

- [ ] UI 개선
  - 헤더에 identity 표시 (UUID 앞 8자리)
  - 송출 권한 표시 배지 ("✓ 송출 권한")
  - 본인 패널만 편집 가능 (readOnly 제어)
  - 송출 버튼 (hasTurn && isMyPanel일 때만 활성화)

### Phase 3: DataChannel 메시지 연동

- [x] `useLiveKit.js` 확장 (별도 훅 대신 통합)
  - `sendData()`: room.localParticipant.publishData() 사용
  - `onDataReceived()`: room.on(RoomEvent.DataReceived) 콜백 등록

- [ ] 메시지 타입 정의
  ```javascript
  // 프론트 → 백엔드
  { type: 'turn.request' }           // 턴 요청
  { type: 'caption.draft', text }    // 임시 자막 입력
  { type: 'caption.broadcast', text } // 송출 요청
  
  // 백엔드 → 프론트
  { type: 'turn.grant', holder }     // 턴 부여
  { type: 'turn.switch', holder }    // 턴 전환 브로드캐스트
  { type: 'caption.broadcast', text } // 송출 텍스트 브로드캐스트
  { type: 'stenographer.list', list } // 속기사 목록 동기화
  ```

### Phase 4: 백엔드 TurnManager 연동

- [ ] `room_agent.py` 수정
  - 참가자 입장 시 역할(participant) → TurnManager 등록
  - 첫 번째 속기사 입장 시 자동 턴 시작
  - 송출 메시지 수신 시 턴 전환 + 브로드캐스트

- [ ] `message_handler.py` 확장
  - `caption.broadcast` 메시지 처리
  - 턴 전환 후 `turn.switch` 브로드캐스트

### Phase 5: 송출 흐름 구현

- [ ] 송출 버튼 클릭 시
  1. 프론트: `caption.broadcast` 메시지 전송
  2. 백엔드: TurnManager.request_turn_switch() 호출
  3. 백엔드: 모든 클라이언트에 `turn.switch` + `caption.broadcast` 전송
  4. 프론트: 송출 텍스트 표시 + 턴 권한 UI 업데이트

---

## 3. 파일 변경 목록

### 프론트엔드
| 파일 | 변경 내용 | 상태 |
|------|----------|------|
| `useLiveKit.js` | localIdentity 반환, sendData/onDataReceived 추가 | ✅ |
| `App.jsx` | 턴 상태 관리, DataChannel 메시지 처리 | ✅ |
| `StenographerPanel/index.jsx` | 송출 권한 UI, 송출 버튼 | ✅ |
| `StenographerPanel/styles.css` | 권한 배지, 버튼 스타일 | ✅ |
| `App.css` | status-identity 스타일 추가 | ✅ |

### 백엔드
| 파일 | 변경 내용 | 상태 |
|------|----------|------|
| `room_agent.py` | 속기사별 텍스트/송출 텍스트 중앙 관리, 퇴장 시 동기화 | ✅ |
| `message_handler.py` | 기존 유지 (RoomMessage 기반) | - |
| `turn_manager.py` | 기존 유지 | - |

---

## 4. 체크리스트

### Phase 1: 프론트엔드 상태 관리
- [x] useLiveKit에서 localParticipant identity 반환
- [x] App.jsx에 턴 관련 상태 추가

### Phase 2: StenographerPanel 기능 확장
- [x] Props 확장 및 UI 개선
- [x] 송출 버튼 추가
- [x] 권한 표시 배지

### Phase 3: DataChannel 메시지 연동
- [x] useLiveKit에 sendData/onDataReceived 추가
- [x] 메시지 송수신 로직 구현

### Phase 4: 백엔드 TurnManager 연동
- [x] 참가자 입장 시 속기사 등록
- [x] 첫 번째 속기사 자동 턴 부여
- [x] caption.broadcast 메시지 처리
- [x] 속기사 목록 브로드캐스트
- [x] 턴 상태 브로드캐스트

### Phase 5: 송출 흐름 구현
- [x] RoomAgent에서 속기사별 텍스트 상태 중앙 관리
- [x] RoomAgent에서 송출 텍스트 중앙 관리
- [x] 참가자 퇴장 시 속기사 목록 즉시 동기화
- [x] 송출 시 발신자 화면도 즉시 업데이트 (DataChannel 제한 해결)
- [x] 턴 전환 시 현재 보유자 제외하여 다음 속기사 선택
- [ ] 전체 플로우 테스트

---

## 5. 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 0.1.0 | 2026-02-26 | 초기 계획서 작성 |
| 0.2.0 | 2026-02-26 | Phase 1~4 구현 완료 |
| 0.3.0 | 2026-02-26 | RoomAgent 중앙 상태 관리 추가, 퇴장 시 동기화 개선 |
| 0.4.0 | 2026-02-26 | 송출 텍스트 공유 및 턴 전환 버그 수정 |
