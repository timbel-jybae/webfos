# LiveKit Ingress 설정 안내

## 실행 순서

1. **Redis 먼저 실행** (redis 폴더에서)
   ```bash
   cd ../redis
   docker compose up -d
   ```

2. **LiveKit 실행** (livekit 폴더에서)
   ```bash
   cd ../livekit
   docker compose up -d
   ```

## Redis 비밀번호

`livekit.yaml`과 `docker-compose.yml`의 redis password는 `redis/docker-compose.yml`의 `REDIS_PASSWORD`와 **동일해야** 합니다.

- 현재: `rDdgtfad3`
- Redis 비밀번호 변경 시 `config/livekit.yaml`과 `docker-compose.yml`(ingress INGRESS_CONFIG_BODY)도 함께 수정하세요.

## 네트워크

- LiveKit Server는 `redis_default` 네트워크에 연결되어 `redis:6379`로 접속
- Ingress는 `network_mode: host`로 `localhost:6379`, `localhost:7880` 사용
