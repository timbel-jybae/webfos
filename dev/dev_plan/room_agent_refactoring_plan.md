# RoomAgent 코드 분리 리팩토링 계획서

## 1. 개요
- **목적**: `room_agent.py` (1472줄)를 기능별 모듈로 분리하여 유지보수성 향상
- **구현 위치**: `src/webfos/agents/`

## 2. 현재 상태 분석

### 현재 구조
```
agents/
├── room_agent.py          # 1472줄 (모든 기능 집중)
├── turn_manager.py        # 턴 관리 (이미 분리됨)
├── caption_manager.py     # 자막 관리 (이미 분리됨)
├── message_handler.py     # 메시지 핸들러 (이미 분리됨)
├── external_connector.py  # 외부 연동 (이미 분리됨)
└── stt_connector.py       # STT 연결 (이미 분리됨)
```

### 분리 대상 기능 그룹
| 그룹 | 메서드 수 | 예상 줄 수 |
|------|----------|-----------|
| STT 처리 | 12개 | ~400줄 |
| 참가자 관리 | 3개 | ~170줄 |
| 메시지 전송 | 5개 | ~120줄 |
| 프론트엔드 메시지 처리 | 8개 | ~340줄 |

## 3. 개발 단계

### Phase 1: STTHandler 분리 (~400줄) ✅ 완료
- [x] `stt_handler.py` 파일 생성
- [x] STTHandler 클래스 구조 설계
- [x] 메서드 이동:
  - `_get_or_create_stt_connector()`
  - `_extract_new_text()`
  - `_on_stt_partial()`
  - `_on_stt_final()`
  - `_broadcast_stt_text()`
  - `_reset_stt_text_state()`
  - `start_stt()` / `stop_stt()`
  - `_start_stt_with_audio_track()`
  - `_resample_audio()`
  - `_calculate_rms()`
- [x] RoomAgent에서 STTHandler 통합
- [x] 기능 테스트
- **결과**: room_agent.py 1472줄 → 1074줄 (약 400줄 감소)

### Phase 2: ParticipantHandler 분리 (~170줄) ✅ 완료
- [x] `participant_handler.py` 파일 생성
- [x] ParticipantHandler 클래스 구조 설계
- [x] 메서드 이동:
  - `_register_participant()`
  - `_unregister_participant()`
  - `_broadcast_stenographer_list()`
- [x] RoomAgent에서 ParticipantHandler 통합
- [x] 기능 테스트
- **결과**: room_agent.py 1074줄 → 934줄 (약 140줄 감소)

### Phase 3: MessageDispatcher 분리 (~120줄) ✅ 완료
- [x] `message_dispatcher.py` 파일 생성
- [x] MessageDispatcher 클래스 구조 설계
- [x] 메서드 이동:
  - `_send_raw_message()`
  - `_send_to_participant()`
  - `_broadcast_turn_state()`
  - `_sync_to_redis()`
- [x] RoomAgent에서 MessageDispatcher 통합
- [x] 기능 테스트
- **결과**: room_agent.py 934줄 → 863줄 (약 71줄 감소)

### Phase 4: FrontendHandler 분리 (~340줄) ✅ 완료
- [x] `frontend_handler.py` 파일 생성
- [x] FrontendHandler 클래스 구조 설계
- [x] 메서드 이동:
  - `_handle_frontend_message()`
  - `_handle_broadcast_request()`
  - `_handle_draft_update()`
  - `_handle_state_request()`
  - `_handle_stt_start()` / `_handle_stt_stop()`
  - `_handle_edit_start()` / `_handle_edit_end()`
- [x] RoomAgent에서 FrontendHandler 통합
- [x] 기능 테스트
- **결과**: room_agent.py 863줄 → 580줄 (약 283줄 감소)

### Phase 5: 정리 및 검증 ✅ 완료
- [x] RoomAgent 최종 정리 (580줄 달성 - 목표 초과)
- [x] `__init__.py` 업데이트
- [x] 전체 통합 테스트
- [x] 불필요한 import 정리

## 6. 최종 결과

| 파일 | 라인 수 | 비고 |
|------|--------|------|
| room_agent.py | 580줄 | 1472줄 → 580줄 (892줄 감소, 60%) |
| stt_handler.py | 496줄 | 신규 |
| participant_handler.py | 243줄 | 신규 |
| message_dispatcher.py | 157줄 | 신규 |
| frontend_handler.py | 347줄 | 신규 |
| **합계** | **1823줄** | 원본 대비 약 350줄 증가 (주석/구조화) |

## 4. 목표 구조

```
agents/
├── room_agent.py          # 중앙 허브 (~350줄)
├── stt_handler.py         # STT 처리 (~400줄) [NEW]
├── participant_handler.py # 참가자 관리 (~170줄) [NEW]
├── message_dispatcher.py  # 메시지 전송 (~120줄) [NEW]
├── frontend_handler.py    # 프론트엔드 메시지 (~340줄) [NEW]
├── turn_manager.py        # 턴 관리 (기존)
├── caption_manager.py     # 자막 관리 (기존)
├── message_handler.py     # 메시지 핸들러 (기존)
├── external_connector.py  # 외부 연동 (기존)
└── stt_connector.py       # STT 연결 (기존)
```

## 5. 설계 원칙

### 의존성 주입
- 각 Handler는 생성 시 필요한 의존성을 주입받음
- RoomAgent가 모든 Handler의 생명주기 관리

### 콜백 패턴
- Handler는 RoomAgent의 메서드를 직접 호출하지 않음
- 필요한 경우 콜백 함수를 주입받아 사용

### 상태 공유
- 공유 상태(room, turn_manager 등)는 RoomAgent에서 관리
- Handler는 필요한 상태를 매개변수로 받거나 참조로 접근

## 6. 주의사항

- 기존 기능이 깨지지 않도록 점진적으로 분리
- 각 Phase 완료 후 반드시 기능 테스트
- 순환 참조 방지
- 타입 힌트 유지
