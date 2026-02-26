# RoomAgent 기능 정의서

## 1. 개요

### 1.1 목적

RoomAgent는 실시간 자막 속기 시스템의 **중앙 허브(Central Hub)** 역할을 수행하는 서버 측 컴포넌트입니다. LiveKit Room 내에서 영상 스트림 관리, 속기사 협업 조정, 자막 데이터 병합, 외부 시스템 연동을 담당합니다.

### 1.2 시스템 컨텍스트

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          외부 시스템                                    │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐  │
│   │ STT 클라이언트 │  │ OCR 클라이언트 │  │ 방송국 자막 수신 시스템    │  │
│   └───────┬───────┘  └───────┬───────┘  └─────────────▲─────────────┘  │
└───────────┼──────────────────┼────────────────────────┼─────────────────┘
            │                  │                        │
            ▼                  ▼                        │
┌─────────────────────────────────────────────────────────────────────────┐
│                       RoomAgent (Central Hub)                           │
│                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │ VideoRouter │ │ TurnManager │ │CaptionMgr   │ │ExternalConnector│   │
│  │ (영상 관리)  │ │ (턴 관리)   │ │(자막 관리)  │ │ (외부 연동)      │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          LiveKit Room                                   │
│     속기사 A ◄────────► RoomAgent ◄────────► 속기사 B                  │
│                             ▲                                           │
│                        검수자 (optional)                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 핵심 책임

| 모듈 | 책임 |
|------|------|
| **VideoRouter** | 영상 스트림 라우팅 (실시간/지연) |
| **TurnManager** | 속기사 턴 관리 및 권한 제어 |
| **CaptionManager** | 자막 데이터 수집, 병합, 저장 |
| **ExternalConnector** | STT/OCR 수신, 방송국 전송 |

---

## 2. 모듈 상세 정의

### 2.1 VideoRouter (영상 관리)

#### 2.1.1 목적

HLS Ingress로 수신된 영상 스트림을 참가자 역할에 따라 적절히 라우팅합니다.

- **속기사**: 실시간 스트림 (저지연)
- **검수자**: 지연 스트림 (3~4초 버퍼)

#### 2.1.2 구성 요소

```python
class VideoRouter:
    """
    영상 스트림 라우팅 관리
    
    Attributes:
        delay_ms: 검수자용 지연 시간 (기본 3500ms)
        video_buffer: 비디오 프레임 링 버퍼
        audio_buffer: 오디오 프레임 링 버퍼
        delayed_video_source: 지연 비디오 출력 소스
        delayed_audio_source: 지연 오디오 출력 소스
    """
    
    def __init__(self, delay_ms: int = 3500):
        """
        VideoRouter 초기화
        
        Args:
            delay_ms: 검수자용 지연 시간 (밀리초)
        """
        pass
    
    async def start(self, room: rtc.Room, ingress_video: rtc.VideoTrack, ingress_audio: rtc.AudioTrack):
        """
        영상 라우팅 시작
        
        - 지연 트랙 생성 및 publish
        - Ingress 트랙 버퍼링 시작
        - 지연 출력 스트림 시작
        """
        pass
    
    async def stop(self):
        """
        영상 라우팅 중지 및 리소스 정리
        """
        pass
    
    def get_current_timestamp(self) -> int:
        """
        현재 영상 타임스탬프 반환 (밀리초)
        
        자막 동기화에 사용
        """
        pass
    
    def get_delayed_timestamp(self) -> int:
        """
        지연된 영상 타임스탬프 반환 (밀리초)
        
        검수자 자막 동기화에 사용
        """
        pass
```

#### 2.1.3 FrameRingBuffer

```python
class FrameRingBuffer:
    """
    고정 시간 윈도우 기반 프레임 링 버퍼
    
    - max_duration_ms 이내의 프레임만 유지
    - 오래된 프레임 자동 삭제 (LRU)
    - 스레드 안전
    """
    
    def __init__(self, max_duration_ms: int):
        """
        Args:
            max_duration_ms: 버퍼 유지 시간 (밀리초)
        """
        pass
    
    async def push(self, frame: Any, timestamp_ms: int):
        """
        프레임 추가
        
        Args:
            frame: 비디오/오디오 프레임
            timestamp_ms: 프레임 타임스탬프
        """
        pass
    
    async def read_delayed(self, delay_ms: int) -> Optional[Tuple[Any, int]]:
        """
        지연된 프레임 읽기
        
        Args:
            delay_ms: 지연 시간
            
        Returns:
            (frame, timestamp_ms) 또는 None
        """
        pass
    
    def clear(self):
        """버퍼 초기화"""
        pass
```

#### 2.1.4 트랙 Identity 규칙

| Identity | 설명 | 구독 대상 |
|----------|------|----------|
| `ingress-hls-source` | HLS Ingress 원본 트랙 | 속기사 |
| `room-agent-delayed` | RoomAgent가 publish하는 지연 트랙 | 검수자 |

---

### 2.2 TurnManager (턴 관리)

#### 2.2.1 목적

속기사들의 작업 턴을 관리하여 자막 작업 충돌을 방지합니다.

- 턴 할당 및 전환
- 작업 권한 제어
- 턴 상태 브로드캐스트

#### 2.2.2 구성 요소

```python
class TurnState(Enum):
    """턴 상태"""
    IDLE = "idle"           # 대기
    ACTIVE = "active"       # 작업 중
    TRANSITIONING = "transitioning"  # 전환 중

@dataclass
class Turn:
    """
    턴 정보
    
    Attributes:
        id: 턴 고유 ID
        holder_identity: 현재 권한 보유 속기사
        start_timestamp_ms: 턴 시작 영상 타임스탬프
        end_timestamp_ms: 턴 종료 영상 타임스탬프 (종료 시 설정)
        state: 턴 상태
        segments: 해당 턴에서 작성된 자막 세그먼트 ID 목록
    """
    id: str
    holder_identity: str
    start_timestamp_ms: int
    end_timestamp_ms: Optional[int]
    state: TurnState
    segments: List[str]

class TurnManager:
    """
    속기사 턴 관리
    
    Attributes:
        current_turn: 현재 활성 턴
        turn_history: 완료된 턴 기록
        participants: 참여 속기사 목록
        turn_duration_ms: 기본 턴 지속 시간 (자동 전환 시)
    """
    
    def __init__(self, turn_duration_ms: int = 30000):
        """
        Args:
            turn_duration_ms: 기본 턴 지속 시간 (밀리초, 자동 전환 모드)
        """
        pass
    
    def register_participant(self, identity: str, role: str):
        """
        참가자 등록
        
        Args:
            identity: 참가자 ID
            role: "stenographer" | "reviewer"
        """
        pass
    
    def unregister_participant(self, identity: str):
        """참가자 등록 해제"""
        pass
    
    def start_turn(self, holder_identity: str, timestamp_ms: int) -> Turn:
        """
        새 턴 시작
        
        Args:
            holder_identity: 턴 권한 부여할 속기사
            timestamp_ms: 시작 영상 타임스탬프
            
        Returns:
            생성된 Turn 객체
        """
        pass
    
    def end_turn(self, timestamp_ms: int) -> Turn:
        """
        현재 턴 종료
        
        Args:
            timestamp_ms: 종료 영상 타임스탬프
            
        Returns:
            종료된 Turn 객체
        """
        pass
    
    def switch_turn(self, next_holder: str, timestamp_ms: int) -> Turn:
        """
        턴 전환 (종료 + 시작 원자적 수행)
        
        Args:
            next_holder: 다음 턴 권한자
            timestamp_ms: 전환 시점 타임스탬프
            
        Returns:
            새로 시작된 Turn 객체
        """
        pass
    
    def request_turn_switch(self, requester_identity: str) -> bool:
        """
        턴 전환 요청 (속기사가 작업 완료 시 호출)
        
        Args:
            requester_identity: 요청자 ID
            
        Returns:
            요청 수락 여부
        """
        pass
    
    def has_permission(self, identity: str) -> bool:
        """
        작업 권한 확인
        
        Args:
            identity: 확인할 참가자 ID
            
        Returns:
            권한 보유 여부
        """
        pass
    
    def get_current_holder(self) -> Optional[str]:
        """현재 턴 권한자 반환"""
        pass
    
    def get_turn_queue(self) -> List[str]:
        """턴 대기열 반환"""
        pass
```

#### 2.2.3 턴 전환 트리거

| 트리거 | 설명 | 우선순위 |
|--------|------|----------|
| 수동 요청 | 속기사가 작업 완료 신호 | 1 |
| 자동 시간 | 설정된 시간 경과 시 자동 전환 | 2 |
| 강제 전환 | 관리자/시스템 명령 | 0 (최우선) |

#### 2.2.4 턴 전환 플로우

```
1. 전환 트리거 발생
        │
        ▼
2. 현재 턴 종료
   - 현재 권한자에게 "turn.end" 신호
   - 미제출 자막 자동 저장
        │
        ▼
3. 다음 턴 시작
   - 대기열에서 다음 속기사 선택
   - "turn.start" 신호 브로드캐스트
   - 권한 부여
        │
        ▼
4. 상태 업데이트
   - turn_history에 완료된 턴 저장
   - current_turn 갱신
```

---

### 2.3 CaptionManager (자막 관리)

#### 2.3.1 목적

속기사로부터 자막 데이터를 수집하고, 병합하여 최종 자막을 생성합니다.

- STT 데이터 수신 및 속기사 전달
- 속기사 자막 수집 및 병합
- 검수자 수정 반영
- 최종 자막 외부 전달

#### 2.3.2 자막 데이터 구조

```python
class CaptionStatus(Enum):
    """자막 상태"""
    DRAFT = "draft"         # 작성 중
    SUBMITTED = "submitted" # 제출됨
    MERGED = "merged"       # 병합됨
    REVIEWED = "reviewed"   # 검수됨
    FINAL = "final"         # 최종 확정

@dataclass
class CaptionSegment:
    """
    자막 세그먼트
    
    Attributes:
        id: 고유 ID (UUID)
        turn_id: 소속 턴 ID
        
        timestamp_start_ms: 시작 타임스탬프 (영상 기준)
        timestamp_end_ms: 종료 타임스탬프
        
        text: 자막 텍스트
        author_identity: 작성자 속기사 ID
        
        stt_reference: STT 원본 텍스트 (참고용)
        ocr_reference: OCR 감지 텍스트 (참고용)
        
        status: 자막 상태
        
        reviewed_by: 검수자 ID (검수된 경우)
        review_note: 검수 메모
        
        created_at: 생성 시각 (서버 시간)
        updated_at: 수정 시각
    """
    id: str
    turn_id: str
    
    timestamp_start_ms: int
    timestamp_end_ms: Optional[int]
    
    text: str
    author_identity: str
    
    stt_reference: Optional[str] = None
    ocr_reference: Optional[str] = None
    
    status: CaptionStatus = CaptionStatus.DRAFT
    
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
```

#### 2.3.3 CaptionManager 인터페이스

```python
class CaptionManager:
    """
    자막 데이터 관리
    
    Attributes:
        caption_buffer: 자막 세그먼트 저장소 (타임스탬프 기반)
        stt_buffer: STT 데이터 버퍼
        merge_engine: 자막 병합 엔진
        retention_ms: 자막 보관 시간
    """
    
    def __init__(self, retention_ms: int = 60000):
        """
        Args:
            retention_ms: 자막 보관 시간 (밀리초)
        """
        pass
    
    # === STT 관련 ===
    
    def receive_stt(self, text: str, timestamp_ms: int, confidence: float):
        """
        STT 결과 수신
        
        Args:
            text: STT 텍스트
            timestamp_ms: 타임스탬프
            confidence: 신뢰도 (0.0 ~ 1.0)
        """
        pass
    
    def get_stt_for_timestamp(self, timestamp_ms: int, window_ms: int = 1000) -> List[dict]:
        """
        특정 시점의 STT 데이터 조회
        
        Args:
            timestamp_ms: 기준 타임스탬프
            window_ms: 조회 범위
        """
        pass
    
    # === 자막 작성 관련 ===
    
    def create_segment(
        self,
        turn_id: str,
        author_identity: str,
        timestamp_start_ms: int,
        text: str,
        stt_reference: Optional[str] = None,
    ) -> CaptionSegment:
        """
        자막 세그먼트 생성
        
        Returns:
            생성된 CaptionSegment
        """
        pass
    
    def update_segment(self, segment_id: str, text: str) -> CaptionSegment:
        """
        자막 세그먼트 수정 (작성 중)
        """
        pass
    
    def submit_segment(self, segment_id: str, timestamp_end_ms: int) -> CaptionSegment:
        """
        자막 세그먼트 제출
        
        Args:
            segment_id: 세그먼트 ID
            timestamp_end_ms: 종료 타임스탬프
        """
        pass
    
    # === 병합 관련 ===
    
    def merge_turn_segments(self, turn_id: str) -> List[CaptionSegment]:
        """
        턴 내 자막 세그먼트 병합
        
        Args:
            turn_id: 턴 ID
            
        Returns:
            병합된 세그먼트 목록
        """
        pass
    
    # === 검수 관련 ===
    
    def review_segment(
        self,
        segment_id: str,
        reviewer_identity: str,
        new_text: Optional[str] = None,
        note: Optional[str] = None,
    ) -> CaptionSegment:
        """
        자막 세그먼트 검수
        
        Args:
            segment_id: 세그먼트 ID
            reviewer_identity: 검수자 ID
            new_text: 수정된 텍스트 (수정 시)
            note: 검수 메모
        """
        pass
    
    def finalize_segment(self, segment_id: str) -> CaptionSegment:
        """
        자막 세그먼트 최종 확정
        """
        pass
    
    # === 조회 관련 ===
    
    def get_segments_for_timestamp(
        self,
        timestamp_ms: int,
        window_ms: int = 500,
        status_filter: Optional[List[CaptionStatus]] = None,
    ) -> List[CaptionSegment]:
        """
        특정 시점의 자막 세그먼트 조회
        
        Args:
            timestamp_ms: 기준 타임스탬프
            window_ms: 조회 범위
            status_filter: 상태 필터 (None이면 전체)
        """
        pass
    
    def get_segments_by_turn(self, turn_id: str) -> List[CaptionSegment]:
        """턴별 자막 세그먼트 조회"""
        pass
    
    def get_final_segments(self, start_ms: int, end_ms: int) -> List[CaptionSegment]:
        """
        최종 확정된 자막 조회 (외부 전달용)
        
        Args:
            start_ms: 시작 타임스탬프
            end_ms: 종료 타임스탬프
        """
        pass
```

---

### 2.4 ExternalConnector (외부 연동)

#### 2.4.1 목적

외부 시스템과의 통신을 담당합니다.

- STT 서비스 연결 및 데이터 수신
- OCR 서비스 연결 및 데이터 수신
- 방송국 자막 전송

#### 2.4.2 구성 요소

```python
class ExternalConnector:
    """
    외부 시스템 연동 관리
    
    Attributes:
        stt_client: STT 서비스 클라이언트
        ocr_client: OCR 서비스 클라이언트
        broadcast_client: 방송국 전송 클라이언트
    """
    
    def __init__(self, config: dict):
        """
        Args:
            config: 외부 연동 설정
        """
        pass
    
    # === STT 연동 ===
    
    async def connect_stt(self, audio_track: rtc.AudioTrack):
        """
        STT 서비스 연결 및 오디오 스트림 전송 시작
        """
        pass
    
    def on_stt_result(self, callback: Callable[[str, int, float], None]):
        """
        STT 결과 콜백 등록
        
        Args:
            callback: (text, timestamp_ms, confidence) -> None
        """
        pass
    
    async def disconnect_stt(self):
        """STT 연결 해제"""
        pass
    
    # === OCR 연동 ===
    
    async def connect_ocr(self, video_track: rtc.VideoTrack):
        """
        OCR 서비스 연결 및 비디오 스트림 전송 시작
        """
        pass
    
    def on_ocr_result(self, callback: Callable[[str, int, dict], None]):
        """
        OCR 결과 콜백 등록
        
        Args:
            callback: (text, timestamp_ms, region) -> None
        """
        pass
    
    async def disconnect_ocr(self):
        """OCR 연결 해제"""
        pass
    
    # === 방송국 전송 ===
    
    async def send_to_broadcast(self, segments: List[CaptionSegment]):
        """
        최종 자막을 방송국 시스템으로 전송
        
        Args:
            segments: 전송할 자막 세그먼트 목록
        """
        pass
    
    def set_broadcast_config(self, config: dict):
        """방송국 전송 설정"""
        pass
```

---

## 3. 통신 프로토콜

### 3.1 DataChannel 메시지 구조

```python
@dataclass
class RoomMessage:
    """
    Room 내 메시지 기본 구조
    """
    type: str               # 메시지 타입
    sender: str             # 발신자 identity
    timestamp: float        # 서버 시간
    payload: dict           # 타입별 페이로드
```

### 3.2 메시지 타입 정의

#### 턴 관련

| 타입 | 방향 | 페이로드 | 설명 |
|------|------|----------|------|
| `turn.start` | Agent → All | `{turn_id, holder, timestamp_ms}` | 턴 시작 알림 |
| `turn.end` | Agent → All | `{turn_id, timestamp_ms}` | 턴 종료 알림 |
| `turn.request` | Stenographer → Agent | `{}` | 턴 전환 요청 |
| `turn.grant` | Agent → Stenographer | `{turn_id}` | 권한 부여 확인 |
| `turn.deny` | Agent → Stenographer | `{reason}` | 권한 거부 |

#### 자막 관련

| 타입 | 방향 | 페이로드 | 설명 |
|------|------|----------|------|
| `caption.draft` | Stenographer → Agent | `{segment}` | 작성 중 자막 (실시간) |
| `caption.submit` | Stenographer → Agent | `{segment_id, timestamp_end_ms}` | 자막 제출 |
| `caption.update` | Agent → All | `{segment}` | 자막 업데이트 알림 |
| `caption.merged` | Agent → All | `{segments}` | 병합 완료 알림 |

#### STT/OCR 관련

| 타입 | 방향 | 페이로드 | 설명 |
|------|------|----------|------|
| `stt.result` | Agent → Stenographers | `{text, timestamp_ms, confidence}` | STT 결과 전달 |
| `ocr.result` | Agent → Stenographers | `{text, timestamp_ms, region}` | OCR 결과 전달 |

#### 검수 관련

| 타입 | 방향 | 페이로드 | 설명 |
|------|------|----------|------|
| `review.edit` | Reviewer → Agent | `{segment_id, new_text, note}` | 검수 수정 |
| `review.approve` | Reviewer → Agent | `{segment_id}` | 검수 승인 |
| `review.result` | Agent → Reviewer | `{segment}` | 검수 결과 |

---

## 4. 상태 관리

### 4.1 RoomAgent 상태

```python
class AgentState(Enum):
    """RoomAgent 상태"""
    INITIALIZING = "initializing"   # 초기화 중
    READY = "ready"                 # 준비 완료
    ACTIVE = "active"               # 활성 (작업 진행 중)
    PAUSED = "paused"               # 일시 정지
    ERROR = "error"                 # 오류 상태
    SHUTTING_DOWN = "shutting_down" # 종료 중
```

### 4.2 상태 전이

```
INITIALIZING ──► READY ──► ACTIVE ◄──► PAUSED
                   │          │
                   │          ▼
                   └──────► ERROR
                              │
                              ▼
                        SHUTTING_DOWN
```

---

## 5. 에러 처리

### 5.1 에러 유형

| 유형 | 설명 | 복구 전략 |
|------|------|----------|
| `INGRESS_DISCONNECTED` | Ingress 연결 끊김 | 재연결 시도 |
| `TRACK_LOST` | 트랙 손실 | 트랙 재구독 |
| `BUFFER_OVERFLOW` | 버퍼 오버플로우 | 오래된 데이터 삭제 |
| `EXTERNAL_SERVICE_ERROR` | 외부 서비스 오류 | 재연결/대체 처리 |
| `PARTICIPANT_TIMEOUT` | 참가자 응답 없음 | 턴 자동 전환 |

### 5.2 복구 절차

```python
class ErrorHandler:
    """
    에러 처리 및 복구 관리
    """
    
    async def handle_ingress_disconnect(self):
        """Ingress 연결 복구"""
        pass
    
    async def handle_track_lost(self, track_sid: str):
        """트랙 손실 복구"""
        pass
    
    async def handle_participant_timeout(self, identity: str):
        """참가자 타임아웃 처리"""
        pass
```

---

## 6. 성능 고려사항

### 6.1 메모리 사용량 예측

| 항목 | 예상 사용량 | 비고 |
|------|------------|------|
| VideoBuffer (3.5초, 1080p) | ~5-10 MB | 프레임 압축 여부에 따라 변동 |
| AudioBuffer (3.5초) | ~1 MB | |
| CaptionBuffer (60초) | ~100 KB | 텍스트 기반 |
| 전체 (채널당) | ~15 MB | |

### 6.2 CPU 사용량

- 프레임 복사/버퍼링: 중간
- 자막 처리: 낮음
- 외부 연동: I/O 바운드

### 6.3 최적화 포인트

1. 프레임 버퍼: Zero-copy 가능 시 활용
2. 자막 인덱싱: 타임스탬프 기반 빠른 조회
3. 배치 처리: 외부 전송 시 배치 단위

---

## 7. 테스트 시나리오

### 7.1 단위 테스트

- [ ] FrameRingBuffer push/read 정확성
- [ ] TurnManager 턴 전환 로직
- [ ] CaptionManager 세그먼트 CRUD
- [ ] 타임스탬프 동기화 정확성

### 7.2 통합 테스트

- [ ] 속기사 2인 턴 교대 시나리오
- [ ] 검수자 지연 영상 + 자막 동기화
- [ ] 외부 시스템 연동 (모의)
- [ ] 장시간 운영 안정성 (1시간+)

### 7.3 부하 테스트

- [ ] 다중 채널 동시 운영
- [ ] 자막 데이터 대량 처리
- [ ] 메모리 누수 검증

---

## 8. 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 0.1.0 | 2026-02-26 | 초기 기능 정의서 작성 |
