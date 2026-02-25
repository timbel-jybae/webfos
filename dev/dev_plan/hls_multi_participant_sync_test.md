# HLS 멀티 참가자 동기화 단위 테스트 계획

> **목적**: 개발초안(개발초안.md) Phase 2 검증 — HLS URL → LiveKit Ingress → 2~3명 참가자가 동일한 싱크의 영상/오디오를 수신하는지 확인

---

## 1. 개요

- **테스트 시나리오**: HLS URL 1개 → Ingress 생성 → Room에 2~3명 참가 → 모든 참가자가 같은 영상/오디오를 실시간으로 시청
- **검증 항목**:
  - [ ] HLS URL로 Ingress 생성 성공
  - [ ] 참가자들이 Room 접속 및 Ingress 트랙 구독 성공
  - [ ] 멀티 참가자 간 영상/오디오 싱크 일치 (육안/체감 확인)

---

## 2. 사전 조건

| 항목 | 설명 |
|------|------|
| LiveKit Server | Docker로 실행 중 (`docker ps` 확인) |
| LiveKit Ingress | HLS 트랜스코딩용 Ingress 서비스 필요 (livekit-ingress 컨테이너) |
| 환경변수 | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| HLS URL | `https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8` (WOW TV 라이브) |

---

## 3. 개발 단계

### Phase 1: HLS Ingress 생성 스크립트

- [x] `dev/test_by_agent/test_hls_ingress_create.py` 작성
  - `livekit-api` Python 패키지 사용
  - `CreateIngressRequest`로 `URL_INPUT` 타입 Ingress 생성
  - HLS URL, Room 이름, Participant Identity/Name 인자로 받기
  - 생성된 Ingress ID 출력

### Phase 2: 참가자 토큰 발급 스크립트

- [x] `dev/test_by_agent/test_token_generator.py` 작성
  - `livekit-api`의 `AccessToken`으로 Room 참가용 JWT 발급
  - Room 이름, Identity, Name 인자로 받기
  - 토큰 + LiveKit URL 출력 (클라이언트 연결용)

### Phase 3: 참가자용 프론트엔드

- [x] `dev/test_by_agent/hls-viewer/` React 앱 작성 (Vite + livekit-client)
  - 로컬 `npm run dev`로 `http://localhost:5173` 접근
  - URL 파라미터로 `token`, `url`(또는 `ws_url`) 받기
  - `TrackSubscribed` 이벤트로 비디오/오디오 트랙 렌더링
- [x] `dev/test_by_agent/test_participant_viewer.html` (HTML 대체용)
  - 참가자 수, 트랙 상태 표시 (디버깅용)

### Phase 4: 통합 테스트 실행 가이드

- [x] `dev/test_by_agent/README_hls_sync_test.md` 작성
  - 실행 순서: 1) Ingress 생성 → 2) 토큰 발급 → 3) 브라우저 탭 2~3개로 접속
  - 환경변수 설정 방법
  - 공개 HLS 테스트 URL 예시

---

## 4. 스크립트 실행 흐름

```
1. 환경변수 설정 (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
2. python test_hls_ingress_create.py --hls-url <HLS_URL> --room <ROOM_NAME>
   → Ingress 생성, Room에 HLS 스트림 퍼블리시
3. python test_token_generator.py --room <ROOM_NAME> --identity participant-1 --name "참가자1"
   → 토큰1 출력
4. (동일 room으로) participant-2, participant-3 토큰 추가 발급
5. test_participant_viewer.html?token=<TOKEN>&url=<WS_URL> 로 브라우저 탭 2~3개 열기
6. 각 탭에서 동일 영상/오디오 재생 여부 확인
```

---

## 5. 클래스/함수 구조 (개념 설계)

### test_hls_ingress_create.py

```python
# create_hls_ingress(hls_url, room_name, participant_identity, participant_name) -> IngressInfo
# - livekit.api.LiveKitAPI().ingress.create_ingress() 호출
# - IngressInput.URL_INPUT, url=hls_url 설정
# - IngressInfo.ingress_id 반환
```

### test_token_generator.py

```python
# generate_token(room_name, identity, name) -> str
# - AccessToken(api_key, api_secret).with_identity().with_name().with_grants()
# - VideoGrants(room_join=True, room=room_name)
# - to_jwt() 반환
```

### test_participant_viewer.html

```javascript
// Room.connect(ws_url, token)
// room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => { track.attach() })
// 비디오/오디오 엘리먼트에 렌더링
```

---

## 6. 확인 사항 (사용자 확인 필요)

- [ ] LiveKit Ingress 컨테이너가 Docker에 포함되어 있는지? (HLS 트랜스코딩에 필수)
- [ ] `LIVEKIT_URL` 형식: `https://...` (API용) vs `wss://...` (클라이언트 WebSocket용) — 보통 API는 https, 클라이언트는 wss
- [ ] 테스트용 HLS URL을 사용자가 직접 제공할지, 공개 샘플 URL 사용할지
