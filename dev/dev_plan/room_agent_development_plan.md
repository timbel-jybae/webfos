# RoomAgent 개발 계획서

## 1. 개요

### 1.1 목적

RoomAgent를 실시간 자막 속기 시스템의 중앙 허브로 재설계하여, 영상 지연 스트리밍, 속기사 턴 관리, 자막 병합, 외부 시스템 연동 기능을 구현합니다.

### 1.2 관련 문서

- 기능 정의서: `dev/docs/room_agent_spec.md`

### 1.3 현재 상태

**✅ 백엔드 핵심 모듈 구현 완료 (Phase 1~4, 6)**

| 모듈 | 상태 | 설명 |
|------|------|------|
| VideoRouter | ❌ 제거됨 | 서버 측 메모리 이슈로 삭제, 클라이언트 측 버퍼링 사용 |
| TurnManager | ✅ 완료 | 속기사 턴 관리, 권한 제어 |
| CaptionManager | ✅ 완료 | 자막 CRUD, 병합, STT/OCR 결과 관리 |
| MessageHandler | ✅ 완료 | DataChannel 메시지 처리 |
| ExternalConnector | ✅ 스켈레톤 | STT/OCR/방송국 연동 인터페이스 |
| RoomAgent | ✅ 완료 | 중앙 허브 통합 |

**🔜 남은 작업**
- Phase 5.2~5.3: 자막 동기화 및 검수 UI (STT 연동 후)
- Phase 7: 프론트엔드 UI 통합
- Phase 8: 테스트 및 안정화

**📋 최근 완료 (2026-02-26)**
- Phase 5.1: 클라이언트 측 지연 버퍼링 개선
  - `useDelayBuffer.js` 큐 기반 순차 처리 로직
  - 서버 측 VideoRouter 대신 클라이언트 측 버퍼링 사용

---

## 2. 개발 단계

### Phase 1: RoomAgent 기반 구조 재설계

목표: RoomAgent 모듈 구조 정립 및 핵심 인프라 구축

**상태: 완료 ✅**

#### 1.1 프로젝트 구조 재정의

- [x] `src/webfos/agents/` 디렉토리 구조 설계
  ```
  agents/
  ├── __init__.py
  ├── room_agent_worker.py    # 엔트리포인트 (기존 파일 수정)
  ├── room_agent.py           # RoomAgent 메인 클래스
  ├── turn_manager.py         # 턴 관리 모듈
  ├── caption_manager.py      # 자막 관리 모듈
  ├── external_connector.py   # 외부 연동 모듈
  ├── message_handler.py      # DataChannel 메시지 처리
  └── models/
      ├── __init__.py
      ├── turn.py             # Turn 데이터 모델
      ├── caption.py          # Caption 데이터 모델
      └── messages.py         # 메시지 프로토콜 모델
  # video_router.py 제거됨 (클라이언트 측 버퍼링 사용)
  ```

- [x] 설정 파일 확장 (`core/config.py`)
  - RoomAgent 관련 설정 추가
  - 지연 시간, 버퍼 크기, 턴 설정 등

#### 1.2 데이터 모델 구현

- [x] `models/turn.py`: Turn, TurnState 모델
- [x] `models/caption.py`: CaptionSegment, CaptionStatus 모델
- [x] `models/messages.py`: RoomMessage 및 메시지 타입 정의

---

### Phase 2: VideoRouter 구현

목표: 영상 스트림 지연 버퍼링 및 검수자용 트랙 publish

**상태: ❌ 제거됨 (2026-02-26)**

> **제거 사유**: 서버 측 raw 프레임 버퍼링으로 인한 메모리 부족 문제
> - 720p에서도 수초 내 수백 MB 메모리 사용
> - **대안**: 클라이언트 측 `useDelayBuffer.js` (MediaRecorder + MediaSource) 사용
> - 관련 파일 삭제: `video_router.py`, `test_video_router.py`, `test_frame_ring_buffer.py`

#### 2.1 FrameRingBuffer 구현

- [x] `video_router.py`에 FrameRingBuffer 클래스 구현
  - 고정 시간 윈도우 기반 링 버퍼
  - asyncio Lock 기반 스레드 안전 처리
  - push(), read_delayed(), clear() 메서드

- [x] 단위 테스트 작성 (`dev/test_by_agent/test_frame_ring_buffer.py`)
  - 버퍼 push/read 정확성
  - 시간 기반 자동 삭제
  - 동시성 테스트

#### 2.2 VideoRouter 구현

- [x] VideoRouter 클래스 구현
  - Ingress 트랙 수신 및 버퍼링
  - 지연 트랙 생성 (VideoSource, AudioSource)
  - 지연 트랙 publish (identity: `room-agent-delayed`)

- [x] 타임스탬프 관리
  - 현재 영상 타임스탬프 추적
  - 지연 영상 타임스탬프 계산

- [x] 단위 테스트 작성 (`dev/test_by_agent/test_video_router.py`)
  - 트랙 publish 확인
  - 지연 시간 정확성

#### 2.3 RoomAgent 통합

- [x] `room_agent.py`에 VideoRouter 통합
- [x] `room_agent_worker.py` 수정
  - VideoRouter 초기화 및 시작
  - Ingress 트랙 연결

---

### Phase 3: TurnManager 구현

목표: 속기사 턴 관리 및 작업 권한 제어

**상태: 완료 ✅**

#### 3.1 TurnManager 기본 구현

- [x] `turn_manager.py` 구현
  - 참가자 등록/해제
  - 턴 시작/종료/전환
  - 권한 확인

- [x] 턴 전환 로직
  - 수동 요청 처리
  - 자동 시간 기반 전환 (옵션)
  - 강제 전환

- [x] 단위 테스트 작성 (`dev/test_by_agent/test_turn_manager.py`)
  - 턴 전환 시나리오
  - 권한 검증
  - 동시성 테스트

#### 3.2 DataChannel 메시지 처리

- [x] `message_handler.py` 구현
  - 턴 관련 메시지 송수신
  - 메시지 직렬화/역직렬화

- [x] RoomAgent 통합
  - TurnManager 초기화
  - 메시지 핸들러 연결

---

### Phase 4: CaptionManager 구현

목표: 자막 데이터 수집, 병합, 관리

**상태: 완료 ✅**

#### 4.1 CaptionManager 기본 구현

- [x] `caption_manager.py` 구현
  - 자막 세그먼트 CRUD
  - 타임스탬프 기반 저장/조회
  - 버퍼 관리 (retention_ms 기반 정리)

- [x] 단위 테스트 작성 (`dev/test_by_agent/test_caption_manager.py`)
  - 세그먼트 생성/수정/제출
  - 타임스탬프 조회

#### 4.2 자막 병합 로직

- [x] MergeEngine 구현 (CaptionManager 내 merge_segments 메서드)
  - 턴 내 세그먼트 병합
  - 타임스탬프 정렬
  - 중복/충돌 처리

- [x] 단위 테스트 작성
  - 병합 시나리오
  - 충돌 해결

#### 4.3 DataChannel 자막 메시지

- [x] 자막 관련 메시지 처리 추가 (`message_handler.py`)
  - draft, submit, update, merged

- [x] RoomAgent 통합
  - CaptionManager 초기화
  - TurnManager와 연동 (턴 종료 시 자막 병합)

---

### Phase 5: 검수자 기능 구현

목표: 검수자용 지연 영상 + 자막 동기화

**상태: 5.1 완료 ✅ (5.2, 5.3은 STT 연동 후 진행)**

#### 5.1 검수자 지연 재생 ✅

> **방식 변경 (2026-02-26)**: 서버 측 VideoRouter → 클라이언트 측 버퍼링
> - 서버 측 raw 프레임 버퍼링은 메모리 문제로 불안정
> - 클라이언트 측 MediaRecorder + MediaSource 방식 사용

- [x] `useDelayBuffer.js` 개선
  - 큐 기반 순차 처리 (버퍼 추가 순서 보장)
  - Promise 기반 대기 (SourceBuffer updating 완료 대기)
  - 에러 복구 로직 (appendBuffer 실패 시 재시도/스킵)
  - 메모리 관리 (QuotaExceededError 처리, 오래된 청크 자동 정리)

- [x] `useLiveKit.js` 수정
  - 검수자/참가자 모두 실시간 트랙(ingress-hls-source) 구독
  - 검수자는 클라이언트에서 useDelayBuffer로 지연 재생

- [x] `App.jsx` 수정
  - 검수자: `DelayedPlayer` 사용 (클라이언트 측 지연)
  - 참가자: `VideoPlayer` 사용 (실시간)

#### 5.2 자막 동기화 표시 (추후 진행 - STT 연동 필요)

- [ ] 프론트엔드 자막 훅 구현 (`useCaptions.js`)
  - DataChannel 자막 수신
  - 현재 영상 타임스탬프에 맞는 자막 필터링

- [ ] 자막 오버레이 컴포넌트 (`CaptionOverlay`)
  - 타임스탬프 동기화 표시
  - 검수 상태 표시

#### 5.3 검수 기능

- [ ] 검수 UI 구현
  - 자막 수정 인터페이스
  - 승인/수정 버튼

- [ ] 검수 메시지 처리
  - review.edit, review.approve 전송
  - 결과 수신 및 반영

---

### Phase 6: 외부 연동 (ExternalConnector)

목표: STT, OCR, 방송국 시스템 연동

**상태: 스켈레톤 구현 완료 (실제 연결 로직은 추후 구현)**

#### 6.1 ExternalConnector 기본 구현

- [x] `external_connector.py` 스켈레톤 구현
  - 연결 관리 인터페이스 (ConnectionState)
  - 콜백 등록 (on_stt_result, on_ocr_result)
  - RoomAgent 통합

#### 6.2 STT 연동 (스켈레톤)

- [x] STT 클라이언트 인터페이스
  - `send_audio_to_stt()` 메서드
  - 콜백 기반 결과 수신 구조

- [x] CaptionManager 연동 구조
  - STT 결과 → CaptionManager 자동 전달

#### 6.3 OCR 연동 (스켈레톤)

- [x] OCR 클라이언트 인터페이스
  - `send_frame_to_ocr()` 메서드
  - 콜백 기반 결과 수신 구조

- [x] CaptionManager 연동 구조
  - OCR 결과 → CaptionManager 자동 전달

#### 6.4 방송국 전송 (스켈레톤)

- [x] 전송 인터페이스
  - `send_caption_to_broadcast()` 메서드
  - 연결 상태 관리

**[TODO] 실제 WebSocket/HTTP 연결 구현 필요**

---

### Phase 7: 프론트엔드 통합

목표: 속기사/검수자 UI 완성

#### 7.1 속기사 UI

- [ ] 턴 상태 표시
  - 현재 턴 홀더
  - 대기열 상태
  - 턴 전환 요청 버튼

- [ ] 자막 입력 인터페이스
  - 텍스트 입력
  - STT 결과 표시
  - 제출 버튼

- [ ] 권한 상태 표시
  - 작업 가능/불가 상태
  - 충돌 경고

#### 7.2 검수자 UI

- [x] 지연 영상 플레이어
  - 클라이언트 측 `DelayedPlayer` + `useDelayBuffer` 사용
  - (서버 측 `room-agent-delayed` 트랙은 메모리 이슈로 비활성화)

- [ ] 자막 표시 (동기화)
  - 현재 영상 시점 자막
  - 상태별 스타일링

- [ ] 검수 인터페이스
  - 수정 입력
  - 승인/수정 버튼

#### 7.3 공통 UI

- [ ] 연결 상태 표시
- [ ] 에러 핸들링 UI
- [ ] 참가자 목록

---

### Phase 8: 테스트 및 안정화

목표: 통합 테스트 및 성능 최적화

#### 8.1 통합 테스트

- [ ] 속기사 2인 턴 교대 시나리오
- [ ] 검수자 지연 영상 + 자막 동기화
- [ ] 외부 시스템 연동 (모의)

#### 8.2 부하 테스트

- [ ] 장시간 운영 테스트 (1시간+)
- [ ] 메모리 누수 검증
- [ ] CPU 사용량 모니터링

#### 8.3 에러 복구 테스트

- [ ] Ingress 연결 끊김 시나리오
- [ ] 참가자 갑작스러운 퇴장
- [ ] 외부 서비스 장애

#### 8.4 문서화

- [ ] API 문서 업데이트
- [ ] 운영 가이드 작성
- [ ] 트러블슈팅 가이드

---

## 3. 기술 스택

### 3.1 백엔드

| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | livekit-agents | 1.0.0+ |
| 런타임 | Python | 3.10+ |
| 비동기 | asyncio | - |
| 데이터 검증 | Pydantic | 2.0+ |

### 3.2 프론트엔드

| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | React | 18.2+ |
| LiveKit | livekit-client | 2.0+ |
| 빌드 | Vite | 5.0+ |

---

## 4. 의존성 추가

### 4.1 백엔드 (requirements.txt 업데이트)

```
# 기존 의존성 유지

# 추가 예정 (필요 시)
# - 외부 STT/OCR 클라이언트 라이브러리
```

### 4.2 프론트엔드 (package.json)

```
# 추가 예정 (필요 시)
# - 자막 관련 UI 라이브러리
```

---

## 5. 마일스톤

| 단계 | 내용 | 산출물 |
|------|------|--------|
| Phase 1 | 기반 구조 | 모듈 구조, 데이터 모델 |
| Phase 2 | 영상 지연 | ~~VideoRouter~~ (제거됨, 클라이언트 측 버퍼링 사용) |
| Phase 3 | 턴 관리 | TurnManager |
| Phase 4 | 자막 관리 | CaptionManager, MergeEngine |
| Phase 5 | 검수 기능 | 검수자 UI, 동기화 로직 |
| Phase 6 | 외부 연동 | ExternalConnector |
| Phase 7 | 프론트엔드 | 속기사/검수자 UI |
| Phase 8 | 안정화 | 테스트, 문서화 |

---

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 방안 |
|--------|------|----------|
| ~~livekit-agents 프레임 버퍼링 성능~~ | ~~지연 트랙 품질 저하~~ | ✅ 해결됨: 클라이언트 측 버퍼링으로 대체 |
| 다중 채널 동시 운영 부하 | 서버 리소스 부족 | 스케일 아웃 설계, 리소스 모니터링 |
| 외부 시스템 연동 지연 | STT 결과 늦음 | 버퍼링, 폴백 로직 |
| 자막 동기화 오차 | 검수 품질 저하 | 타임스탬프 보정 로직 |

---

## 7. 체크리스트

### Phase 1: 기반 구조
- [x] 디렉토리 구조 생성
- [x] 데이터 모델 구현 (Turn, Caption, Message)
- [x] 설정 파일 확장

### Phase 2: VideoRouter (❌ 제거됨)
- [x] ~~FrameRingBuffer 구현~~ (삭제됨)
- [x] ~~FrameRingBuffer 단위 테스트~~ (삭제됨)
- [x] ~~VideoRouter 구현~~ (삭제됨)
- [x] ~~VideoRouter 단위 테스트~~ (삭제됨)
- [x] ~~RoomAgent 통합~~ (제거됨 - 클라이언트 측 버퍼링 사용)

### Phase 3: TurnManager
- [x] TurnManager 구현
- [x] TurnManager 단위 테스트
- [x] DataChannel 메시지 처리
- [x] RoomAgent 통합

### Phase 4: CaptionManager
- [x] CaptionManager 기본 구현
- [x] CaptionManager 단위 테스트
- [x] MergeEngine 구현
- [x] DataChannel 자막 메시지
- [x] RoomAgent 통합

### Phase 5: 검수자 기능
- [x] 프론트엔드 지연 트랙 구독 수정 (`useLiveKit.js`, `App.jsx`)
- [ ] useCaptions 훅 구현 (STT 연동 후)
- [ ] CaptionOverlay 컴포넌트 (STT 연동 후)
- [ ] 검수 UI 구현 (STT 연동 후)

### Phase 6: 외부 연동 (스켈레톤)
- [x] ExternalConnector 기본 구현
- [x] STT 연동 인터페이스
- [x] OCR 연동 인터페이스
- [x] 방송국 전송 인터페이스
- [ ] 실제 연결 구현 (추후)

### Phase 7: 프론트엔드 통합
- [ ] 속기사 UI (턴/자막/권한)
- [ ] 검수자 UI (지연 영상/자막/검수)
- [ ] 공통 UI (연결 상태/에러)

### Phase 8: 테스트 및 안정화
- [ ] 통합 테스트
- [ ] 부하 테스트
- [ ] 에러 복구 테스트
- [ ] 문서화

---

## 8. 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 0.1.0 | 2026-02-26 | 초기 개발 계획서 작성 |
| 0.2.0 | 2026-02-26 | Phase 1~4, 6 완료 (백엔드 핵심 모듈 구현) |
| 0.2.1 | 2026-02-26 | Phase 5.1 완료 (검수자 지연 트랙 구독) |
| 0.2.2 | 2026-02-26 | Phase 5.1 방식 변경 (서버→클라이언트 측 버퍼링) |
| 0.2.3 | 2026-02-26 | VideoRouter 코드 완전 제거 (메모리 이슈로 폐기) |
