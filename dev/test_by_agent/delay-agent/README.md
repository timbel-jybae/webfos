# LiveKit 지연 Agent

룸 내부 스트림(ingress-hls-source)을 구독하여 3.5초 버퍼 후 재발행합니다.
검수자는 이 Agent의 지연 트랙만 구독합니다.

## 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정 (backend/.env 또는 delay-agent/.env)
# LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
# BACKEND_URL=http://localhost:32055 (토큰 발급용)

python main.py
```

## 동작

1. 백엔드 `/api/agent-token`에서 토큰 발급
2. 룸 접속 (identity: delay-agent)
3. `ingress-hls-source` 참가자의 비디오/오디오 트랙 구독
4. LRU 링 버퍼에 3.5초 저장
5. 지연된 프레임을 VideoSource/AudioSource로 재발행
6. 검수자는 delay-agent의 트랙만 구독

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| LIVEKIT_URL | LiveKit 서버 URL | - |
| LIVEKIT_API_KEY | API 키 | - |
| LIVEKIT_API_SECRET | API 시크릿 | - |
| BACKEND_URL | 토큰 발급 API | http://localhost:32055 |
| ROOM_NAME | 대상 룸 이름 | hls-sync-test-room |
