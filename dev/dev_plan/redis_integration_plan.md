# Redis 연동 개발 계획

## 1. 개요

- **목적**: RoomAgent 내부 상태를 Admin 대시보드에서 조회할 수 있도록 Redis를 통한 상태 공유
- **데이터 관리**: TTL 기반 자동 만료, 서버 시작 시 초기화

## 2. 개발 단계

### Phase 1: Redis 클라이언트 설정
- [x] Redis 의존성 추가 (redis-py)
- [x] config.py에 Redis 설정 추가 (host, port, db)
- [x] RedisClient 클래스 생성 (`clients/redis_client.py`)
- [x] 연결 테스트 및 에러 핸들링

### Phase 2: 키 구조 및 TTL 정의
- [x] 키 네이밍 컨벤션 정의
- [x] 데이터 타입별 TTL 설정
- [x] RedisKeys 헬퍼 클래스 생성

### Phase 3: RoomAgent → Redis 저장
- [x] 턴 상태 저장 (turn.grant, turn.switch)
- [x] 속기사 목록 저장 (stenographer.list)
- [x] 속기사 텍스트 저장 (caption.draft)
- [x] 송출 텍스트 저장 (caption.broadcast)
- [x] 송출 이력 저장 (broadcast_history)

### Phase 4: Admin API → Redis 조회
- [x] 룸 상세 API에 RoomAgent 상태 추가
- [x] 실시간 모니터링 데이터 제공
- [x] 프론트엔드에서 상태 표시

### Phase 5: 초기화 및 정리
- [x] 서버 시작 시 webfos:* 키 삭제
- [x] RoomAgent 종료 시 해당 룸 키 삭제

## 3. 키 구조 설계

```
webfos:room:{room_name}:state
  - stenographers: [{ identity, text }]
  - turn_holder: "identity"
  - broadcast_text: "text"
  - updated_at: timestamp

webfos:room:{room_name}:history
  - List: [{ text, sender, timestamp }, ...]
```

## 4. TTL 정책

| 키 패턴 | TTL | 설명 |
|---------|-----|------|
| `webfos:room:*:state` | 3600s (1시간) | 세션 상태 |
| `webfos:room:*:history` | 86400s (24시간) | 송출 이력 |

## 5. 서버 초기화 로직

```python
# main.py lifespan 시작 시
await redis_client.delete_pattern("webfos:*")
```

## 6. 파일 구조

```
src/webfos/
├── clients/
│   └── redis_client.py      # Redis 클라이언트 (신규)
├── core/
│   └── config.py            # Redis 설정 추가
├── agents/
│   └── room_agent.py        # Redis 저장 로직 추가
├── api/endpoints/
│   └── admin_endpoints.py   # Redis 조회 로직 추가
└── main.py                  # 초기화 로직 추가
```
