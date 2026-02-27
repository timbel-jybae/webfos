# STT 연동 개발 계획

## 1. 개요

- **목적**: WhisperLive 실시간 STT를 RoomAgent에 연동
- **STT 서버**: `ws://192.168.1.249:9090` (WhisperLive)
- **모델**: `Systran/faster-whisper-large-v3` (한국어 지원)
- **특징**: 지속 WebSocket 연결, 서버 측 VAD, 실시간 파셜 결과

## 2. 요구사항

1. RoomAgent에 STT 상태 플래그 (내부 관리)
2. STT 수행 중 파셜(partial) 결과를 Room 내 broadcast
3. 속기사(프론트엔드)는 STT 결과를 받아서 화면에 표시

## 3. 개발 단계

### Phase 1: STTConnector 클래스 생성
- [x] `agents/stt_connector.py` 생성
- [x] ~~WebSocket 연결 관리 (Speaches Realtime API)~~ → WhisperLive API로 변경
- [x] 오디오 데이터 전송 메서드 (PCM16 → float32 변환)
- [x] Transcription 결과 콜백 처리 (partial, final)

### Phase 2: RoomAgent STT 상태 관리
- [x] `_stt_enabled: bool` 플래그 추가
- [x] `_stt_partial_text: str` 파셜 텍스트 상태
- [x] STT 시작/중지 메서드

### Phase 3: 오디오 트랙 처리
- [x] Ingress 오디오 트랙 구독
- [x] 오디오 프레임을 STTConnector로 전달
- [x] PCM16 → float32 포맷 변환

### Phase 4: STT 결과 Broadcast
- [x] `stt.partial` 메시지 타입 정의
- [x] 파셜 결과 실시간 broadcast
- [x] `stt.final` 완료 결과 broadcast

### Phase 5: 프론트엔드 STT 표시
- [x] DataChannel에서 `stt.partial` 수신 처리
- [x] STT 텍스트 상태 추가
- [x] UI에 STT 결과 표시 (별도 영역)

### Phase 6: WhisperLive 전환 (신규)
- [x] Docker 이미지 변경 (`ghcr.io/collabora/whisperlive-gpu:latest`)
- [x] STTConnector WhisperLive 프로토콜 적용
- [x] 지속 WebSocket 연결 구현
- [x] 서버 측 VAD 활성화
- [ ] 단위 테스트 실행 및 검증

## 4. 메시지 형식

### RoomAgent → 프론트엔드

```json
// 파셜 결과 (실시간)
{
  "type": "stt.partial",
  "text": "안녕하세요 오늘",
  "timestamp": 1234567890
}

// 최종 결과 (문장 완료)
{
  "type": "stt.final",
  "text": "안녕하세요 오늘 날씨가 좋습니다.",
  "timestamp": 1234567890
}
```

## 5. 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        RoomAgent                             │
├─────────────────────────────────────────────────────────────┤
│  _stt_enabled: bool                                          │
│  _stt_partial_text: str                                      │
│  stt_connector: STTConnector                                 │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ AudioTrack   │───>│ STTConnector │───>│ broadcast()  │   │
│  │ (Ingress)    │    │ (WebSocket)  │    │ stt.partial  │   │
│  │ PCM16        │    │ float32 변환  │    │ stt.final    │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 지속 WebSocket 연결
                    ┌─────────────────┐
                    │  WhisperLive    │
                    │  STT Server     │
                    │  (VAD 내장)      │
                    └─────────────────┘
```

## 6. 설정 (config.py)

```python
# STT 설정 (WhisperLive)
STT_ENABLED: bool = True
STT_WS_URL: str = "ws://192.168.1.249:9090"
STT_MODEL: str = "Systran/faster-whisper-large-v3"
STT_LANGUAGE: str = "ko"
```

## 7. WhisperLive 프로토콜

### 연결 시 설정 전송
```json
{
  "uid": "uuid-string",
  "language": "ko",
  "task": "transcribe",
  "model": "Systran/faster-whisper-large-v3",
  "use_vad": true
}
```

### 오디오 전송
- 형식: **float32 바이너리** (PCM16에서 변환)
- 샘플레이트: 16kHz, mono
- 지속적으로 스트리밍

### 결과 수신
```json
{
  "uid": "...",
  "segments": [
    {"text": "안녕하세요", "start": 0.0, "end": 1.5, "completed": false},
    {"text": "오늘 날씨가", "start": 1.5, "end": 3.0, "completed": false}
  ]
}
```

## 8. 파일 구조

```
src/webfos/agents/
├── stt_connector.py      # WhisperLive WebSocket 클라이언트
├── room_agent.py         # STT 상태 관리
└── external_connector.py # (기존 스켈레톤)

~/Documents/Docker-composes/faster-whisper/
└── docker-compose.yml    # WhisperLive 도커 설정

dev/test_by_agent/
└── test_whisperlive_connector.py  # STTConnector 단위 테스트
```
