# HLS 지연 프록시

검수자용 3.5초 지연 HLS 스트림 제공. LiveKit 지연 Ingress가 이 URL을 소스로 사용.

## 실행 순서

1. **HLS 지연 프록시** (먼저 실행)
2. **백엔드** (Ingress 2개 생성)
3. **프론트엔드** (테스트)

## 실행

```bash
cd dev/test_by_agent/hls-delay-proxy
pip install -r requirements.txt
python server.py
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| HLS_SOURCE_URL | wowtv HLS | 소스 HLS URL |
| DELAY_SEC | 3.5 | 지연 시간(초) |
| PORT | 9999 | 서버 포트 |

## LiveKit Docker 환경

LiveKit Ingress가 지연 프록시에 접근하려면 **호스트에서 실행 중인 프록시**로의 URL이 필요합니다.

**백엔드 `.env`에 추가:**

```bash
# Mac/Windows Docker Desktop
HLS_DELAY_PROXY_URL=http://host.docker.internal:9999/playlist.m3u8

# Linux Docker (host.docker.internal 없음)
# 호스트 IP 사용: ip addr show docker0 | grep inet
HLS_DELAY_PROXY_URL=http://172.17.0.1:9999/playlist.m3u8
# 또는 docker run 시: --add-host=host.docker.internal:host-gateway
```

**확인:** `ingress-hls-delayed`가 룸에 없으면 이 URL에 LiveKit이 접근하지 못하는 것입니다.
