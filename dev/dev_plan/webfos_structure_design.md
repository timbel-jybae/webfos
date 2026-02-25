# Webfos 구조 설계 계획서

> **목적**: LiveKit 기반 실시간 영상 동기화 시스템의 정식 개발 구조 설계
> **기반**: 단위 테스트(`dev/test_by_agent/`) 검증 결과 + `architecture_guide.md` 방침

---

## 1. 개요

### 1.1 서비스 구성
| 서비스 | 경로 | 역할 |
|--------|------|------|
| **webfos** (백엔드) | `src/webfos/` | FastAPI 기반 API 서버, LiveKit 연동 |
| **webfos_frontend** | `src/webfos_frontend/` | React 기반 클라이언트, 영상 재생 |

### 1.2 핵심 기능
- **실시간 영상 동기화**: HLS → LiveKit Ingress → WebRTC → 다중 클라이언트
- **검수자 지연 재생**: 클라이언트 측 3.5초 버퍼링 (MediaRecorder + MediaSource)
- **화질 선택**: 1~8Mbps 비트레이트 설정

---

## 2. 개발 단계

### Phase 1: 백엔드 구조 구축
- [x] 1.1 디렉토리 구조 생성 (`src/webfos/`)
- [x] 1.2 `core/config.py` - 환경변수 설정 (Pydantic Settings)
- [x] 1.3 `clients/livekit_client.py` - LiveKit API 클라이언트
- [x] 1.4 `managers/room_manager.py` - 룸 상태 관리 싱글톤
- [x] 1.5 `services/room_service.py` - 룸/Ingress 비즈니스 로직
- [x] 1.6 `api/schemas/room_schemas.py` - 요청/응답 스키마
- [x] 1.7 `api/endpoints/room_endpoints.py` - REST API 라우터
- [x] 1.8 `api/endpoints/health_endpoints.py` - 헬스체크
- [x] 1.9 `main.py` - FastAPI 엔트리포인트

### Phase 2: 프론트엔드 구조 구축
- [x] 2.1 디렉토리 구조 생성 (`src/webfos_frontend/`)
- [x] 2.2 Vite + React 프로젝트 설정
- [x] 2.3 `hooks/useLiveKit.js` - LiveKit 연결 훅
- [x] 2.4 `hooks/useDelayBuffer.js` - 지연 버퍼 훅
- [x] 2.5 `components/VideoPlayer/` - 실시간 비디오 컴포넌트
- [x] 2.6 `components/DelayedPlayer/` - 검수자 지연 플레이어
- [x] 2.7 `components/QualitySelector/` - 화질 선택 UI
- [x] 2.8 `components/ConnectionPanel/` - 연결 패널
- [x] 2.9 `App.jsx` 통합 및 라우팅

### Phase 3: 아키텍처 개선 (채널 선택)
- [x] 3.1 `managers/channel_manager.py` - 채널 관리 싱글톤
- [x] 3.2 `api/schemas/channel_schemas.py` - 채널 API 스키마
- [x] 3.3 `api/endpoints/channel_endpoints.py` - 채널 목록/입장 API
- [x] 3.4 프론트엔드 채널 선택 UI (`App.jsx` 수정)
- [x] 3.5 `api/roomApi.js` - 채널 API 호출 함수

### Phase 4: 영상 재생 문제 수정
- [x] 4.1 VideoPlayer: `track.attach()` 반환값 사용 방식으로 변경
- [x] 4.2 useDelayBuffer: 순환 의존성 및 중복 실행 방지
- [x] 4.3 DelayedPlayer: useEffect 의존성 배열 정리
- [x] 4.4 useLiveKit: React Strict Mode 연결 중복 방지
- [x] 4.5 서버 시작 시 Ingress 미리 생성 (channel_manager.initialize_all_ingresses)
- [x] 4.6 채널 입장 시 기존 Ingress 사용

### Phase 5: 통합 및 안정화
- [ ] 5.1 백엔드-프론트엔드 연동 테스트
- [ ] 5.2 다중 참가자 동기화 테스트
- [ ] 5.3 검수자 지연 재생 안정성 검증
- [ ] 5.4 에러 처리 및 복구 로직 추가

---

## 3. 백엔드 상세 설계 (`src/webfos/`)

### 3.1 디렉토리 구조

```
src/webfos/
├── main.py                         # FastAPI 엔트리포인트, lifespan 관리
├── core/
│   └── config.py                   # Pydantic Settings (환경변수 기반 설정)
│
├── api/                            # [Layer 1] API 어댑터 레이어
│   ├── endpoints/
│   │   ├── room_endpoints.py       # 룸 생성, 토큰 발급, Ingress 관리
│   │   ├── channel_endpoints.py    # 채널 목록/입장 API
│   │   └── health_endpoints.py     # 헬스체크 (/health, /ready)
│   └── schemas/
│       ├── room_schemas.py         # PrepareRequest, PrepareResponse 등
│       └── channel_schemas.py      # ChannelInfo, ChannelJoinResponse 등
│
├── services/                       # [Layer 2] 비즈니스 서비스 레이어
│   └── room_service.py             # 룸 생성, Ingress 연동, 토큰 발급 로직
│
├── managers/                       # [싱글톤] 상태 관리
│   ├── room_manager.py             # 활성 룸/Ingress 상태 추적
│   └── channel_manager.py          # 채널 목록 관리 (하드코딩 → 추후 DB)
│
└── clients/                        # [외부 연동] LiveKit API
    ├── base_client.py              # HTTP 클라이언트 베이스 (스켈레톤 복사)
    └── livekit_client.py           # LiveKit Server/Ingress API 호출
```

### 3.2 주요 클래스/함수 설계

#### `core/config.py`
```python
class Settings(BaseSettings):
    """
    환경변수 기반 설정
    - LIVEKIT_URL: LiveKit 서버 WebSocket URL
    - LIVEKIT_API_KEY: API 인증 키
    - LIVEKIT_API_SECRET: API 시크릿
    - HLS_SOURCE_URL: 기본 HLS 소스 URL
    """
    pass
```

#### `clients/livekit_client.py`
```python
class LiveKitClient:
    """
    LiveKit Server API 클라이언트
    - create_room(): 룸 생성
    - delete_room(): 룸 삭제
    - create_ingress(): HLS Ingress 생성
    - delete_ingress(): Ingress 삭제
    - generate_token(): 참가자 토큰 발급
    """
    pass
```

#### `managers/room_manager.py`
```python
class RoomManager:
    """
    활성 룸 상태 관리 싱글톤
    - _rooms: Dict[room_name, RoomState]
    - get_or_create(): 룸 조회 또는 생성
    - cleanup(): 비활성 룸 정리
    """
    pass
```

#### `services/room_service.py`
```python
class RoomService:
    """
    룸 관리 비즈니스 로직
    - prepare(): 룸 + Ingress 생성 + 참가자 토큰 발급
    - get_room_status(): 룸 상태 조회
    - cleanup_room(): 룸 정리
    """
    pass
```

#### `api/endpoints/room_endpoints.py`
```python
# POST /api/prepare - 룸 준비 (Ingress + 토큰 발급)
# GET /api/rooms/{room_name}/status - 룸 상태 조회
# DELETE /api/rooms/{room_name} - 룸 삭제
```

---

## 4. 프론트엔드 상세 설계 (`src/webfos_frontend/`)

### 4.1 디렉토리 구조

```
src/webfos_frontend/
├── package.json
├── vite.config.js
├── index.html
├── .env.example
└── src/
    ├── main.jsx                    # React 엔트리포인트
    ├── App.jsx                     # 메인 앱 컴포넌트
    ├── App.css                     # 전역 스타일
    │
    ├── components/
    │   ├── VideoPlayer/
    │   │   ├── index.jsx           # 실시간 비디오 플레이어
    │   │   └── styles.css
    │   ├── DelayedPlayer/
    │   │   ├── index.jsx           # 검수자용 지연 플레이어
    │   │   └── styles.css
    │   ├── QualitySelector/
    │   │   ├── index.jsx           # 화질 선택 드롭다운
    │   │   └── styles.css
    │   └── ConnectionPanel/
    │       ├── index.jsx           # 연결 UI (상태, 버튼)
    │       └── styles.css
    │
    ├── hooks/
    │   ├── useLiveKit.js           # LiveKit Room 연결 관리
    │   └── useDelayBuffer.js       # MediaRecorder + MediaSource 버퍼 관리
    │
    ├── utils/
    │   ├── mediaRecorder.js        # MediaRecorder 헬퍼
    │   └── constants.js            # 상수 (QUALITY_OPTIONS 등)
    │
    └── api/
        └── roomApi.js              # 백엔드 API 호출
```

### 4.2 주요 훅/컴포넌트 설계

#### `hooks/useLiveKit.js`
```javascript
/**
 * LiveKit Room 연결 관리 훅
 * - connect(wsUrl, token): 룸 연결
 * - disconnect(): 연결 해제
 * - room: Room 인스턴스
 * - connectionState: 연결 상태
 * - participants: 참가자 목록
 * - videoTrack, audioTrack: 구독된 트랙
 */
```

#### `hooks/useDelayBuffer.js`
```javascript
/**
 * 검수자용 지연 버퍼 관리 훅
 * - startBuffer(videoTrack, audioTrack, quality): 버퍼링 시작
 * - stopBuffer(): 버퍼링 중지
 * - delayedVideoRef: 지연 비디오 엘리먼트 ref
 * - isReady: 버퍼 준비 완료 여부
 * - play(): 지연 비디오 재생
 */
```

#### `components/DelayedPlayer/index.jsx`
```javascript
/**
 * 검수자용 지연 플레이어
 * Props:
 * - videoTrack: 원본 비디오 트랙
 * - audioTrack: 원본 오디오 트랙
 * - quality: 선택된 화질
 * - delayMs: 지연 시간 (기본 3500ms)
 */
```

---

## 5. 환경 설정

### 5.1 백엔드 `.env`
```env
# LiveKit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# HLS Source
HLS_SOURCE_URL=https://example.com/stream.m3u8

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### 5.2 프론트엔드 `.env`
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_DEFAULT_DELAY_MS=3500
```

---

## 6. 의존성

### 6.1 백엔드 (`requirements.txt`)
```
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic-settings>=2.0.0
livekit-api>=0.5.0
httpx>=0.24.0
python-dotenv>=1.0.0
```

### 6.2 프론트엔드 (`package.json`)
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "livekit-client": "^2.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0"
  }
}
```

---

## 7. 참고 자료

- 단위 테스트 코드: `dev/test_by_agent/backend/`, `dev/test_by_agent/hls-viewer/`
- 아키텍처 가이드: `dev/docs/architecture_guide.md`
- 스켈레톤 코드: `dev/reference/skeleton/`
- 개발 초안: `dev/dev_plan/개발초안.md`
