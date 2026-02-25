# HLS 멀티 참가자 동기화 테스트 가이드

개발초안(개발초안.md) Phase 2 검증: HLS URL → LiveKit Ingress → 2~3명 참가자가 동일한 싱크의 영상/오디오를 수신하는지 확인합니다.

---

## 1. 사전 요구사항

### 1.1 LiveKit 인프라

- **LiveKit Server**: Docker로 실행 중 (`docker ps`로 확인)
- **Redis**: **필수**. LiveKit Server와 Ingress가 동일한 Redis를 사용해야 함
- **LiveKit Ingress**: HLS 트랜스코딩용 Ingress 서비스 필요
  - `livekit-ingress` 컨테이너가 별도로 실행되어 있어야 함
  - Ingress는 Redis 메시지 큐로 LiveKit Server와 통신 ([공식 문서](https://docs.livekit.io/transport/self-hosting/ingress/))

### 1.2 Python 의존성

```bash
# conda 환경 활성화 후
pip install livekit-api
```

### 1.3 환경변수 (.env)

`.env.example`을 복사하여 `.env` 생성 후 값 설정:

```bash
cp dev/test_by_agent/.env.example dev/test_by_agent/.env
# 또는 backend 사용 시
cp dev/test_by_agent/backend/.env.example dev/test_by_agent/backend/.env
```

| 변수 | 필수 | 설명 |
|------|------|------|
| `LIVEKIT_URL` | O | LiveKit API URL (https://) |
| `LIVEKIT_API_KEY` | O | API Key |
| `LIVEKIT_API_SECRET` | O | API Secret |
| `HLS_URL` | - | HLS 스트림 URL (기본: WOW TV) |
| `PORT` | - | 백엔드 포트 (기본: 32055) |

- **참고**: 클라이언트 연결 시 `LIVEKIT_URL`을 `wss://`로 변환하여 사용.

---

## 2. 테스트용 HLS URL

| URL | 설명 |
|-----|------|
| `https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8` | **WOW TV 라이브** (기본값) |

---

## 3. 실행 순서 (통합 플로우)

### Step 1: .env 설정

```bash
cd dev/test_by_agent
cp .env.example .env
# .env 편집: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET 입력
```

### Step 2: 백엔드 실행

```bash
cd dev/test_by_agent/backend
pip install -r requirements.txt
python server.py
```

- `.env` 자동 로드 (backend/.env 또는 dev/test_by_agent/.env)
- 서버 기동 시 **Ingress 자동 생성** (HLS → Room)
- `http://localhost:32055` (또는 PORT 값) 에서 API 대기

### Step 3: 프론트엔드 실행

```bash
cd dev/test_by_agent/hls-viewer
npm install
npm run dev
```

- `http://localhost:5173` 접속
- **"테스트 시작"** 클릭 → 백엔드에서 토큰 준비
- **참가자 1**: "이 탭에서 접속" → 현재 탭에서 룸 입장
- **참가자 2, 3**: "새 탭에서 접속" → 새 탭으로 룸 입장

---

### (참고) CLI로 개별 실행

```bash
# Ingress만 생성
python test_hls_ingress_create.py --room "hls-sync-test-room"

# 토큰만 발급
python test_token_generator.py --room "hls-sync-test-room" --identity "participant-1" --output-url
```

### Step 4: 동기화 확인

- 2~3개 탭에서 동시에 접속
- 각 탭에 Ingress에서 퍼블리시한 영상/오디오가 표시되는지 확인
- **싱크 검증**: 여러 탭의 영상이 같은 시점을 재생하는지 육안으로 확인 (예: 동일한 장면이 동시에 보이는지)

---

## 4. LiveKit 인프라 설정 (Redis 필수)

Ingress 사용 시 **Redis 필수**. LiveKit Server와 Ingress가 **동일한 Redis**를 사용해야 함.

**Ingress config 예시** (`config.yaml`):

```yaml
api_key: <YOUR_API_KEY>
api_secret: <YOUR_API_SECRET>
ws_url: ws://localhost:7880
redis:
  address: localhost:6379   # LiveKit Server와 동일
```

**Docker Compose 예시**:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  livekit-server:
    image: livekit/livekit-server
    # redis 연결 설정

  livekit-ingress:
    image: livekit/ingress
    # 동일 redis 연결 설정
```

[공식 문서](https://docs.livekit.io/transport/self-hosting/ingress/)

---

## 5. 트러블슈팅

| 증상 | 가능 원인 | 조치 |
|------|----------|------|
| `ingress not connected (redis required)` | Redis 미설정 또는 Ingress-Server 간 Redis 불일치 | 위 "LiveKit 인프라 설정" 참고 |
| Ingress 생성 실패 | Ingress 서비스 미실행 | `livekit-ingress` 컨테이너 확인 |
| 토큰 오류 | API Key/Secret 불일치 | 환경변수 재확인 |
| 연결 실패 (브라우저) | WebSocket URL 오류 | `wss://` 사용, 포트 확인 |
| 영상 미표시 | Ingress 버퍼링/트랜스코딩 지연 | 30초~1분 대기 후 재시도 |
| CORS/보안 오류 | file:// 프로토콜 제한 | 로컬 HTTP 서버 사용 |

---

## 6. 파일 목록

| 파일 | 역할 |
|------|------|
| `backend/server.py` | FastAPI 백엔드 (기동 시 Ingress 생성, `/api/prepare`, `/api/token`) |
| `backend/requirements.txt` | 백엔드 의존성 |
| `backend/.env.example` | 백엔드 환경변수 템플릿 |
| `.env.example` | 통합 환경변수 템플릿 (dev/test_by_agent/) |
| `hls-viewer/` | React 참가자 뷰어 (백엔드 API 연동) |
| `test_hls_ingress_create.py` | CLI: HLS Ingress 생성 |
| `test_token_generator.py` | CLI: 토큰 발급 |
| `test_participant_viewer.html` | HTML 참가자 뷰어 (대체용) |
| `README_hls_sync_test.md` | 본 가이드 |
