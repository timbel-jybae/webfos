# 관리자 대시보드 (webfos_admin) 개발 계획

## 1. 개요

- **목적**: 채널/룸 현황 모니터링 및 관리를 위한 관리자 전용 프론트엔드
- **구현 위치**: `src/webfos_admin/`
- **데이터 소스**: LiveKit API (main.py의 기존 엔드포인트 + 신규 API)
- **인증**: 1단계에서는 스킵 (추후 추가)

## 2. 개발 단계

### Phase 1: 프로젝트 초기 설정
- [x] Vite + React 프로젝트 생성 (`src/webfos_admin/`)
- [x] 기본 의존성 설치 (react-router-dom 등)
- [x] 개발 서버 포트 설정 (5174, webfos_frontend와 충돌 방지)
- [x] 기본 레이아웃 컴포넌트 생성 (사이드바 + 메인 콘텐츠)

### Phase 2: 백엔드 API 확장
- [x] 룸 목록 조회 API 추가 (`GET /api/admin/rooms`)
  - LiveKit API로 전체 룸 목록 조회
  - 각 룸의 참가자 수, 상태 정보 포함
- [x] 룸 상세 조회 API 추가 (`GET /api/admin/rooms/{room_name}`)
  - 룸의 참가자 목록 (identity, role, 연결 시간 등)
  - 트랙 정보

### Phase 3: 대시보드 메인 화면
- [x] 채널/룸 카드 목록 컴포넌트
  - 채널명, 룸 상태, 참가자 수 표시
  - 실시간 갱신 (polling 또는 interval)
- [x] 전체 현황 요약 (총 룸 수, 총 참가자 수 등)

### Phase 4: 룸 상세 화면
- [x] 룸 선택 시 상세 정보 패널
  - 참가자 목록 (속기사/검수자 구분)
  - 연결 상태, 입장 시간
- [x] 룸 내 참가자 실시간 갱신

### Phase 5: 스타일링 및 UX 개선
- [ ] 다크 모드 기본 적용
- [ ] 반응형 레이아웃
- [ ] 로딩/에러 상태 표시

## 3. 컴포넌트 구조 (개념 설계)

```
src/webfos_admin/
├── src/
│   ├── App.jsx                 # 메인 앱 (라우팅)
│   ├── App.css
│   ├── main.jsx
│   ├── components/
│   │   ├── Layout/             # 사이드바 + 메인 레이아웃
│   │   │   ├── index.jsx
│   │   │   └── styles.css
│   │   ├── RoomCard/           # 룸 요약 카드
│   │   │   ├── index.jsx
│   │   │   └── styles.css
│   │   ├── RoomDetail/         # 룸 상세 패널
│   │   │   ├── index.jsx
│   │   │   └── styles.css
│   │   └── ParticipantList/    # 참가자 목록
│   │       ├── index.jsx
│   │       └── styles.css
│   ├── hooks/
│   │   └── useAdminApi.js      # API 호출 훅
│   └── services/
│       └── adminApi.js         # API 클라이언트
├── index.html
├── package.json
└── vite.config.js
```

## 4. API 설계 (개념)

### 4.1 룸 목록 조회
```
GET /api/admin/rooms

Response:
{
  "rooms": [
    {
      "name": "channel-kbs1",
      "sid": "RM_xxx",
      "num_participants": 3,
      "created_at": "2026-02-26T14:00:00Z",
      "metadata": { ... }
    }
  ],
  "total": 10
}
```

### 4.2 룸 상세 조회
```
GET /api/admin/rooms/{room_name}

Response:
{
  "name": "channel-kbs1",
  "sid": "RM_xxx",
  "participants": [
    {
      "identity": "p-abc123",
      "name": "속기사1",
      "role": "stenographer",
      "joined_at": "2026-02-26T14:05:00Z",
      "tracks": [...]
    }
  ]
}
```

## 5. 제한사항 (1단계)

- RoomAgent 내부 상태 (턴, 텍스트 등)는 조회 불가
- 실시간 업데이트는 polling 방식 (WebSocket 미사용)
- 로그인/권한 관리 없음

## 6. 추후 확장 (2단계)

- Redis 연동으로 RoomAgent 상태 조회
- WebSocket으로 실시간 업데이트
- 속기사 배정 관리 기능
- 인증/권한 관리
