# Webfos v2 프로젝트 분석

## 개요
**실시간 자막 협업 시스템** — 방송 영상에 대해 속기사와 검수자가 협업하여 자막을 작성하는 플랫폼.

---

## 아키텍처

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│  Frontend   │   │    Admin     │   │   Backend    │
│  (React)    │   │  Dashboard   │   │  (FastAPI)   │
│  :5173      │   │  (React)     │   │  :32055      │
└──────┬──────┘   └──────┬───────┘   └──────┬───────┘
       │                 │                   │
       └────────┬────────┘                   │
                │ REST API                   │
                ▼                            │
       ┌────────────────┐          ┌─────────▼────────┐
       │  LiveKit Server │◄────────│  Agent Worker    │
       │  :7880          │         │  (RoomAgent)     │
       └────────┬────────┘         └─────────┬────────┘
                │                            │
       ┌────────▼────────┐          ┌────────▼────────┐
       │  LiveKit Ingress│          │     Redis       │
       │  (HLS→Room)    │          │   (상태 공유)    │
       └─────────────────┘          └─────────────────┘
                                            │
                                    ┌───────▼────────┐
                                    │  WhisperLive   │
                                    │  (STT, :30010) │
                                    └────────────────┘
```

---

## 핵심 컴포넌트

### 1. Backend (`src/webfos/`) — Python/FastAPI

| 모듈 | 역할 |
|------|------|
| `main.py` | FastAPI 엔트리포인트, Lifespan으로 Ingress/Redis 초기화 |
| `agents/room_agent.py` | **중앙 허브** — 턴/자막/메시지/STT 관리 |
| `agents/turn_manager.py` | 속기사 간 턴(작업 권한) 관리 |
| `agents/caption_manager.py` | 자막 세그먼트 CRUD 및 병합 |
| `agents/stt_handler.py` | WhisperLive STT 처리 |
| `agents/stt_connector.py` | WhisperLive WebSocket 연결 |
| `agents/message_dispatcher.py` | DataChannel 메시지 전송 + Redis 동기화 |
| `agents/frontend_handler.py` | 프론트엔드 메시지 수신/처리 |
| `agents/participant_handler.py` | 참가자 입퇴장 관리 |
| `clients/` | LiveKit, Redis 클라이언트 |
| `managers/` | Room/Channel 관리 |

### 2. Frontend (`src/webfos_frontend/`) — React/Vite

- **속기사 뷰**: 실시간 영상 + 속기 패널 2개 + 송출 텍스트
- **검수자 뷰**: 3.5초 지연 영상 (클라이언트 측 MediaRecorder 버퍼링)
- LiveKit DataChannel로 실시간 턴/자막/STT 상태 동기화

### 3. Admin (`src/webfos_admin/`) — React/Vite

- Room/참가자 모니터링 대시보드

---

## 주요 기능 흐름

1. **HLS Ingress**: HLS 스트림 → LiveKit Room으로 영상 입수
2. **턴 기반 속기**: 속기사 간 턴 권한 관리, 한 번에 1명만 송출 가능
3. **STT 지원**: WhisperLive(Whisper large-v3) WebSocket 연결로 음성→텍스트 자동 입력, 편집 모드 지원
4. **실시간 동기화**: DataChannel로 모든 참가자에게 턴/자막/STT 상태 실시간 전파
5. **Redis 상태 공유**: API 서버와 Agent Worker 간 상태 공유

---

## 기술 스택

### 백엔드

| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | FastAPI | 0.100+ |
| 실시간 통신 | LiveKit | - |
| Agent | livekit-agents | 1.0+ |
| 런타임 | Python | 3.11+ |
| 상태 저장 | Redis | 7 (Alpine) |
| STT | WhisperLive (Whisper large-v3) | WebSocket |
| HTTP 클라이언트 | httpx | 0.24+ |
| 로깅 | loguru | 0.7+ |

### 프론트엔드

| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | React | 18.2+ |
| LiveKit | livekit-client | 2.0+ |
| 빌드 | Vite | 5.0+ |

---

## 인프라

- **Docker Compose** 기반 (dev/prod 오버레이 구성)
- 6개 서비스: Redis, LiveKit, Ingress, API, Worker, Frontend, Admin
- LiveKit agents 프레임워크의 Rust FFI 메모리 이슈가 알려진 문제

---

## 사용자 역할

| 역할 | 설명 | 영상 | 기능 |
|------|------|------|------|
| 속기사 | 자막 입력 담당 | 실시간 | 턴 기반 자막 입력 |
| 검수자 | 자막 검수 담당 | 3.5초 지연 | 자막 확인/수정/승인 |

---

## DataChannel 메시지 타입

| 메시지 | 방향 | 설명 |
|--------|------|------|
| `stenographer.list` | Agent → Client | 속기사 목록 동기화 |
| `turn.grant` / `turn.switch` | Agent → Client | 턴 권한 부여/전환 |
| `caption.draft` | Client → Agent → Client | 임시 텍스트 브로드캐스트 |
| `caption.broadcast` | Client → Agent → Client | 송출 텍스트 확정 |
| `stt.start` / `stt.stop` | Client → Agent | STT 시작/중지 요청 |
| `stt.text` | Agent → Client | STT 결과 (확정 + 입력 중) |
| `stt.partial` / `stt.final` | Agent → Client | STT 부분/최종 결과 |
| `stt.status` | Agent → Client | STT 상태 알림 |
| `edit.start` / `edit.end` | Client → Agent | 편집 모드 시작/종료 |
| `state.request` | Client → Agent | 초기 상태 요청 |

---

## 현재 개발 상태 (2026-03-17 기준)

- RoomAgent 리팩토링 완료 (Phase 1~4: STT/Participant/MessageDispatcher/FrontendHandler 분리)
- Docker 컨테이너화 작업 진행 중 (Dockerfile, docker-compose, nginx 설정 추가)
- STT 편집 모드 기능 구현 완료
- 아직 커밋되지 않은 변경사항 다수 존재
