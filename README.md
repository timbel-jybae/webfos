# Webfos - 실시간 자막 협업 시스템

실시간 방송 영상에 대한 속기사-검수자 협업 자막 시스템입니다.

## 주요 기능

- **실시간 영상 스트리밍**: HLS 소스를 LiveKit Room으로 Ingress
- **검수자용 지연 재생**: 클라이언트 측 버퍼링으로 3.5초 지연된 영상 제공
- **턴 기반 속기**: 속기사 간 작업 권한 관리 (TurnManager)
- **자막 관리**: 자막 세그먼트 CRUD 및 병합 (CaptionManager)
- **DataChannel 메시징**: 실시간 턴/자막 상태 동기화

## 기술 스택

### 백엔드
| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | FastAPI | 0.100+ |
| 실시간 통신 | LiveKit | - |
| Agent | livekit-agents | 1.4+ |
| 런타임 | Python | 3.11+ |

### 프론트엔드
| 구분 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | React | 18.2+ |
| LiveKit | livekit-client | 2.0+ |
| 빌드 | Vite | 5.0+ |

## 프로젝트 구조

```
webpos/
├── src/
│   ├── webfos/                 # 백엔드
│   │   ├── api/                # FastAPI 엔드포인트
│   │   ├── agents/             # RoomAgent 중앙 허브
│   │   │   ├── room_agent.py
│   │   │   ├── room_agent_worker.py
│   │   │   ├── turn_manager.py
│   │   │   ├── caption_manager.py
│   │   │   ├── message_handler.py
│   │   │   ├── external_connector.py
│   │   │   └── models/
│   │   ├── services/
│   │   ├── clients/
│   │   └── core/
│   └── webfos_frontend/        # 프론트엔드
│       └── src/
│           ├── components/
│           │   ├── VideoPlayer/
│           │   ├── DelayedPlayer/
│           │   └── QualitySelector/
│           └── hooks/
│               ├── useLiveKit.js
│               └── useDelayBuffer.js
└── dev/
    ├── dev_plan/               # 개발 계획서
    └── docs/                   # 기능 정의서
```

## 설치

### 1. 환경 설정

```bash
# Conda 환경 생성 (Python 3.11 권장)
conda create -n webpos python=3.11
conda activate webpos

# 백엔드 의존성 설치
cd src/webfos
pip install -r requirements.txt

# 프론트엔드 의존성 설치
cd ../webfos_frontend
npm install
```

### 2. 환경 변수 설정

`src/webfos/.env` 파일 생성:

```env
# LiveKit 설정
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# HLS 소스
HLS_SOURCE_URL=https://example.com/stream.m3u8
DEFAULT_ROOM_NAME=webfos-room

# 서버 설정
HOST=0.0.0.0
PORT=32055
DEBUG=true
```

## 실행

### 1. LiveKit 서버 실행

```bash
livekit-server --dev
```

### 2. 백엔드 실행

```bash
cd src/webfos

# FastAPI 서버
python main.py

# RoomAgent Worker (별도 터미널)
python -m agents.room_agent_worker dev
```

### 3. 프론트엔드 실행

```bash
cd src/webfos_frontend
npm run dev
```

## 사용자 역할

| 역할 | 설명 | 영상 | 기능 |
|------|------|------|------|
| 속기사 | 자막 입력 담당 | 실시간 | 턴 기반 자막 입력 |
| 검수자 | 자막 검수 담당 | 3.5초 지연 | 자막 확인/수정/승인 |

## API 엔드포인트

### 채널 관리
- `POST /api/channels` - 채널 생성 (HLS Ingress 시작)
- `GET /api/channels` - 채널 목록 조회
- `DELETE /api/channels/{channel_id}` - 채널 삭제

### Room 토큰
- `POST /api/room/token` - 참가자 토큰 발급

## 알려진 이슈

### livekit-agents 메모리 문제

**증상:**
```
malloc(): unaligned tcache chunk detected
corrupted size vs. prev_size
process exited with non-zero exit code -6
```

**상태:** livekit-agents 프레임워크 자체 버그 (미해결)

**관련 GitHub 이슈:**
- [livekit/agents#3841](https://github.com/livekit/agents/issues/3841) - Worker processes dying silently
- [livekit/python-sdks#563](https://github.com/livekit/python-sdks/issues/563) - FfiQueue memory leak

**임시 대응:**
- 프로세스 재시작으로 일시적 해결
- 트랙 구독 최소화 권장

**영향:**
- 다중 Room 연결 시 간헐적 Agent 프로세스 크래시
- 네이티브(Rust) FFI 바인딩 메모리 손상으로 추정

---

### VideoRouter 제거 (2026-02-26)

서버 측 VideoRouter(영상 지연 버퍼링)는 메모리 문제로 제거되었습니다.
- 720p에서도 수초 내 수백 MB 메모리 사용
- 대안: 클라이언트 측 `useDelayBuffer.js` (MediaRecorder + MediaSource)

## 개발 문서

- [개발 계획서](dev/dev_plan/room_agent_development_plan.md)
- [기능 정의서](dev/docs/room_agent_spec.md)

## 라이선스

Private - Timbel
