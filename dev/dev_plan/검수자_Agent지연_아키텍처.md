# 검수자 LiveKit Agent 지연 아키텍처

## 1. 개요

- **목적**: 룸 내부 스트림 기준으로 정확히 3~4초 지연 보장
- **방식**: LiveKit Agent가 룸에 참가 → 실시간 트랙 구독 → LRU 링 버퍼 → 지연 트랙 재발행
- **효과**: 속기사가 보는 화면과 검수자 화면의 싱크가 정확히 3.5초 차이

## 2. 아키텍처

```
[ HLS Ingress ] ----> Room (실시간)
        |                  |
        |                  +----> [ 속기사 1~3 ] (실시간 구독)
        |                  |
        |                  +----> [ Delay Agent ] ----> 버퍼(3.5초) ----> 지연 트랙 발행
        |                                    |                    |
        |                                    +--------------------+----> [ 검수자 ] (지연만 구독)
```

## 3. 버퍼 구조 (LRU 개념)

- **입력**: 실시간 트랙의 VideoFrame / AudioFrame
- **저장**: `(frame, timestamp)` → 링 버퍼 (고정 크기)
- **출력**: `timestamp + DELAY_SEC` 경과 시 버퍼에서 꺼내 VideoSource/AudioSource에 push
- **용량**: 3.5초 분량 (예: 30fps 비디오 = 105 프레임, 오디오 = 샘플 수에 따라)

## 4. 개발 단계

### Phase 1: Agent 기본 구조
- [x] `dev/test_by_agent/delay-agent/` 생성
- [x] livekit, livekit-api 의존성
- [x] 룸 연결 (토큰은 백엔드 `/api/agent-token`에서 발급)
- [x] `ingress-hls-source` 트랙만 구독

### Phase 2: 버퍼 및 재발행
- [x] VideoFrame 링 버퍼 (LRU, 크기 제한)
- [x] AudioFrame 링 버퍼 (LRU, 크기 제한)
- [x] VideoSource, AudioSource 생성 및 publish
- [x] 버퍼에서 꺼낸 프레임을 delay 후 push

### Phase 3: 백엔드/프론트 연동
- [x] 백엔드: Agent 토큰 발급 API (`/api/agent-token`) 추가
- [x] Agent: 토큰 발급 후 룸 참가
- [x] 프론트: `delay-agent` 우선 구독, 없으면 `ingress-hls-delayed` (기존 HLS 프록시)

## 5. 기술 스택

- **livekit**: Room, VideoStream, AudioStream, VideoSource, AudioSource
- **livekit-api**: Agent용 토큰 발급 (또는 기존 _generate_token 활용)
