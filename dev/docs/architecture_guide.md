# Timbel 프로젝트 공통 개발 아키텍처 가이드

> **목적**: AI 에이전트 및 개발자가 **일관된 구조**로 개발을 이어갈 수 있도록 레이어 구조, 책임 분리, 디자인 패턴을 정의한 **자립적(self-contained) 문서**입니다.
>
> **이 문서만으로** 아키텍처 규칙을 파악할 수 있어야 하며, 별도의 외부 레퍼런스 프로젝트를 참조할 필요가 없습니다.
>
> **스켈레톤 코드**: `dev/reference/skeleton/` 에 직접 복사·확장할 수 있는 베이스 클래스 스켈레톤이 있습니다. 신규 프로젝트 시작 시 이 스켈레톤을 기반으로 구조를 잡습니다.

---

## 1. 프로젝트 디렉토리 구조 (표준 템플릿)

```
src/<service_name>/
├── main.py                         # FastAPI 엔트리포인트, lifespan 관리
├── core/
│   ├── config.py                   # Pydantic Settings (환경변수 기반 설정)
│   └── celery.py                   # Celery 앱 설정 + Beat 스케줄 (선택적)
│
├── api/                            # [Layer 1] API 어댑터 레이어
│   ├── endpoints/                  # REST/WebSocket 라우터
│   │   ├── <domain>_endpoints.py
│   │   └── ws_endpoints.py
│   ├── schemas/                    # Pydantic 요청/응답 스키마 (DTO)
│   │   └── <domain>_schemas.py
│   └── grpc/                       # gRPC 서버 (선택적)
│
├── services/                       # [Layer 2] 비즈니스 서비스 레이어
│   ├── <domain>_service.py         # 메인 도메인 서비스
│   ├── stream_service.py           # 스트리밍 등 부가 서비스
│   └── stream_dto.py               # 서비스 간 전달 DTO
│
├── managers/                       # [싱글톤] 상태/생명주기 관리 매니저
│   ├── session_manager.py          # 세션 상태 관리
│   ├── model_registry.py           # 모델 등록/관리
│   └── scheduler.py                # 백그라운드 스케줄러
│
├── clients/                        # [외부 연동] 외부 API/서비스 호출 클라이언트
│   ├── base_client.py              # HTTP 클라이언트 공통 베이스
│   ├── <external>_client.py        # 외부 서비스별 클라이언트
│   └── ...
│
├── pipeline/                       # [Layer 3] 파이프라인 레이어 (해당 시)
│   ├── pipeline_orchestrator.py    # 파이프라인 오케스트레이터
│   ├── pipeline_context.py         # Context Object (단계 간 데이터 전달)
│   ├── decorators.py               # @stage_timer 등 파이프라인 데코레이터
│   └── stages/                     # 독립 Stage 모듈
│       ├── <stage_1>/
│       ├── <stage_2>/
│       └── ...
│
├── workers/                        # [비동기 작업] Celery 태스크 (선택적)
│   └── tasks.py                    # 태스크 정의 (Beat 스케줄 / On-Demand)
│
├── db/                             # [Layer 4] 데이터 영속성 레이어
│   ├── database.py                 # SQLAlchemy 엔진/세션 관리
│   ├── base/
│   │   ├── base_repository.py      # Generic CRUD 레포지토리
│   │   └── base_service.py         # 트랜잭션 관리 베이스 서비스
│   ├── models/                     # SQLAlchemy ORM 모델
│   │   └── <domain>_model.py
│   ├── repositories/               # 도메인별 레포지토리
│   │   └── <domain>_repository.py
│   └── services/                   # 도메인별 DB 서비스
│       └── <domain>_service.py
│
└── dev/                            # 개발 전용 (배포 시 제외)
    ├── dev_plan/                   # 개발 계획서
    ├── docs/                       # 아키텍처/설명 문서
    ├── reference/                  # 참고 자료 (사용자 관리)
    ├── scripts/                    # 실행 스크립트 (사용자 관리)
    └── test_by_agent/              # AI 에이전트 작성 테스트
```

---

## 2. 레이어 구조 및 의존성 방향

### 2.1 4계층 아키텍처

```
┌─────────────────────────────────────────────┐
│  [Layer 1] API 레이어  (api/)               │  ← 외부 진입점 (HTTP)
│  REST / WebSocket / gRPC 어댑터             │
├─────────────────────────────────────────────┤
│  [Layer 1'] Workers 레이어  (workers/)      │  ← 외부 진입점 (비동기)
│  Celery 태스크 + Beat 스케줄                  │
├─────────────────────────────────────────────┤
│  [Layer 2] 서비스 레이어  (services/)        │  ← 비즈니스 로직
│  도메인 서비스 + DTO 변환                     │
├──────────────┬──────────────────────────────┤
│  [Layer 3]   │  managers/  │  clients/      │  ← 보조 레이어
│  Pipeline    │  싱글톤     │  외부 API      │
│  (pipeline/) │  매니저     │  클라이언트     │
├──────────────┴──────────────────────────────┤
│  [Layer 4] DB 레이어  (db/)                 │  ← 데이터 영속성
│  Repository + DB Service + ORM Model        │
├─────────────────────────────────────────────┤
│  [공통] core/config.py + core/celery.py     │  ← 설정 (모든 레이어에서 참조)
└─────────────────────────────────────────────┘
```

> **Workers는 API와 동급**이다. 둘 다 "외부 진입점"이며, 내부적으로 Service/Pipeline/DB를 호출한다. Workers에 비즈니스 로직을 넣지 않는다.

### 2.2 의존성 방향 규칙

```
API ──┐
      ├──→ Service → Pipeline → DB
Workers┘         ↓
            managers / clients
```

| 규칙 | 설명 |
|------|------|
| **상위→하위만 참조** | API는 Service를 호출하고, Service는 Pipeline/DB를 호출한다. 역방향 참조 금지. |
| **동일 레이어 간 참조 최소화** | 같은 레이어 내 모듈 간 직접 참조를 피하고, 상위 레이어에서 조합한다. |
| **순환 참조 방지** | 불가피한 경우 함수 내부 지연 import(`from ... import ...`)를 사용한다. |
| **core/config는 예외** | 설정은 모든 레이어에서 직접 참조 가능하다. |

---

## 3. 각 레이어의 책임과 규칙

### 3.1 API 레이어 (`api/`)

**역할**: 외부 프로토콜(HTTP, WebSocket, gRPC)을 내부 서비스 호출로 변환하는 **얇은 어댑터**.

**규칙**:
- 비즈니스 로직을 포함하지 않는다. 스키마 변환과 서비스 호출만 담당한다.
- `endpoints/`에 FastAPI Router를 정의한다.
- `schemas/`에 Pydantic 모델로 요청/응답 DTO를 정의한다.
- 에러는 `HTTPException`으로 변환하여 반환한다.

**구조 예시**:
```python
# api/endpoints/<domain>_endpoints.py
router = APIRouter()

@router.post("/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    """Pydantic 스키마 → 서비스 호출 → 응답 스키마 변환"""
    result = domain_service.process(request.text)
    return ProcessResponse.from_result(result)
```

```python
# api/schemas/<domain>_schemas.py
class ProcessRequest(BaseModel):
    """요청 스키마 — API 계약 정의"""
    text: str
    mode: ProcessMode = ProcessMode.DEFAULT

class ProcessResponse(BaseModel):
    """응답 스키마 — 클라이언트에 반환되는 구조"""
    output: str
    latency_ms: float
```

---

### 3.2 서비스 레이어 (`services/`)

**역할**: 비즈니스 로직의 진입점. 파이프라인, DB, 매니저, 클라이언트를 조합하여 도메인 유스케이스를 구현한다.

**규칙**:
- 하나의 서비스 클래스는 하나의 도메인 책임을 가진다.
- 프로토콜(HTTP/WS/gRPC)에 의존하지 않는다 — 동일 서비스를 여러 어댑터가 호출할 수 있어야 한다.
- 내부적으로 Pipeline, DB Service, Manager, Client를 조합한다.

**구조 예시**:
```python
# services/<domain>_service.py
class DomainService:
    """
    도메인 비즈니스 로직의 진입점.
    Pipeline 오케스트레이터를 래핑하고,
    DB/Manager/Client를 조합하여 유스케이스를 구현한다.
    """
    def __init__(self):
        self.pipeline = PipelineOrchestrator()
    
    def process(self, text: str, mode: str = "default") -> Dict[str, Any]:
        """단건 처리 — 파이프라인 실행 + 결과 변환"""
        ctx = self.pipeline.process(text, config={"mode": mode})
        return ctx.to_dict()
    
    def get_health(self) -> Dict[str, Any]:
        """서비스 상태 점검"""
        ...

# 모듈 레벨 인스턴스 (API에서 import하여 사용)
domain_service = DomainService()
```

---

### 3.3 매니저 (`managers/`)

**역할**: 싱글톤 패턴으로 **상태 관리, 생명주기 관리, 백그라운드 작업**을 담당한다.

**규칙**:
- 모든 싱글톤 인스턴스는 `managers/` 하위에 위치한다.
- 모듈 레벨에서 인스턴스를 생성하여 export한다.
- 상태를 가지는 객체(세션, 레지스트리, 스케줄러 등)만 매니저로 분류한다.
- 서비스 레이어에서 import하여 사용한다.

**구조 예시**:
```python
# managers/session_manager.py
class SessionManager:
    """
    활성 세션 상태를 관리하는 싱글톤 매니저.
    생성/조회/만료 정리를 담당한다.
    """
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
    
    def get_or_create(self, session_id: str) -> SessionState:
        """세션 조회 또는 생성"""
        ...
    
    def cleanup_expired(self) -> int:
        """만료 세션 정리, 정리된 수 반환"""
        ...

# 싱글톤 인스턴스
session_manager = SessionManager()
```

```python
# managers/scheduler.py
class BackgroundScheduler:
    """
    주기적 백그라운드 작업을 관리하는 싱글톤 스케줄러.
    """
    def start(self, interval_seconds: int, run_on_startup: bool = False):
        """스케줄러 시작"""
        ...
    
    def stop(self):
        """스케줄러 중지"""
        ...

# 싱글톤 인스턴스
scheduler = BackgroundScheduler()
```

**매니저에 해당하는 것**:
- `SessionManager` — 세션 상태 관리
- `ModelRegistry` — 모델 등록/버전 관리
- `BackgroundScheduler` — 주기적 작업 스케줄링
- `ConnectionPool` — 커넥션 풀 관리
- `CacheManager` — 캐시 관리

---

### 3.4 클라이언트 (`clients/`)

**역할**: 외부 API/서비스와의 통신을 캡슐화한다. HTTP, gRPC, SDK 호출 등을 **내부 인터페이스로 추상화**한다.

**규칙**:
- 외부 서비스 호출은 반드시 `clients/` 하위에 클라이언트 클래스로 작성한다.
- `base_client.py`에 공통 HTTP 로직(타임아웃, 재시도, 에러 핸들링)을 정의한다.
- 각 외부 서비스별로 전용 클라이언트를 작성하고, 베이스를 상속한다.
- 외부 응답은 내부 DTO/Dict로 변환하여 반환한다 — 외부 응답 구조가 서비스 레이어까지 전파되지 않도록 한다.
- 서비스 레이어에서 import하여 사용한다. API 레이어에서 직접 호출하지 않는다.

**구조 예시**:
```python
# clients/base_client.py
import httpx
from core.config import settings

class BaseClient:
    """
    외부 API 호출 공통 베이스.
    타임아웃, 재시도, 에러 핸들링을 공통으로 처리한다.
    """
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """지연 초기화된 HTTP 클라이언트 반환"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client
    
    async def _request(self, method: str, path: str, **kwargs) -> Dict:
        """공통 요청 처리 — 재시도, 에러 래핑 포함"""
        ...
    
    async def close(self):
        """클라이언트 리소스 정리"""
        if self._client:
            await self._client.aclose()
```

```python
# clients/livekit_client.py
class LiveKitClient(BaseClient):
    """
    LiveKit Server API 클라이언트.
    룸 생성/삭제, 참가자 관리, 토큰 발급 등을 담당한다.
    """
    def __init__(self):
        super().__init__(
            base_url=settings.LIVEKIT_API_URL,
            timeout=settings.LIVEKIT_TIMEOUT,
        )
    
    async def create_room(self, room_name: str, max_participants: int) -> Dict:
        """룸 생성 — 외부 응답을 내부 Dict로 변환하여 반환"""
        ...
    
    async def generate_token(self, room_name: str, identity: str) -> str:
        """참가자 토큰 발급"""
        ...

# 싱글톤 (managers/ 가 아닌 clients/ 에 위치)
livekit_client = LiveKitClient()
```

**클라이언트에 해당하는 것**:
- 외부 REST API 호출 (LiveKit, STT, TTS, 우리말샘 등)
- 외부 gRPC 서비스 호출
- 외부 SDK 래핑 (AWS S3, Redis 등)
- 서드파티 라이브러리의 네트워크 호출 추상화

---

### 3.5 파이프라인 레이어 (`pipeline/`)

**역할**: 다단계 데이터 처리 흐름을 구성한다. 각 Stage는 독립적이고, Orchestrator가 흐름을 제어한다.

**규칙**:
- 파이프라인이 필요 없는 단순 서비스에서는 이 레이어를 생략할 수 있다.
- 반드시 3가지 구성요소를 갖는다: **Orchestrator**, **Context**, **Stages**.

#### 3.5.1 `@stage_timer` 데코레이터 (필수 기본 패턴)

모든 `_run_<stage>()` 메서드에 **반드시** `@stage_timer("stage_name")`를 붙인다. 데코레이터가 자동으로 처리하는 것:
1. 실행 시간 측정
2. `loguru`로 Stage명 + 소요시간 로깅 (`[Pipeline] detection 완료: 3.2ms`)
3. `StageSnapshot` 자동 생성 + Context에 추가

따라서 `_run_<stage>()` 메서드 내부에는 **순수 Stage 로직만** 작성하면 된다.

```python
# pipeline/decorators.py
def stage_timer(stage_name: str):
    """
    Stage 실행 시간을 자동으로 측정·로깅·스냅샷하는 데코레이터.

    동작:
        1. ctx.current_text를 input_text로 캡처
        2. 래핑된 메서드 실행
        3. 실행 시간 측정 → logger.info 출력
        4. StageSnapshot 생성 → ctx.add_snapshot() 자동 호출
        5. 수정된 ctx 반환
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, ctx: PipelineContext, *args, **kwargs) -> PipelineContext:
            input_text = ctx.current_text
            start = time.time()

            ctx = func(self, ctx, *args, **kwargs)

            duration_ms = (time.time() - start) * 1000
            logger.info(f"[Pipeline] {stage_name} 완료: {duration_ms:.1f}ms")

            ctx.add_snapshot(stage_name, StageSnapshot(
                stage_name=stage_name,
                input_text=input_text,
                output_text=ctx.current_text,
                metadata=kwargs.get("metadata", {}),
                duration_ms=duration_ms,
            ))
            return ctx
        return wrapper
    return decorator
```

#### 3.5.2 Pipeline Orchestrator

전체 파이프라인 흐름을 제어하는 **지휘자**. Stage 모듈을 순차/조건부 실행한다. 각 `_run_<stage>()` 메서드에 `@stage_timer`를 붙여 시간 측정을 자동화한다.

```python
# pipeline/pipeline_orchestrator.py
from pipeline.decorators import stage_timer

class PipelineOrchestrator:
    """
    N단계 파이프라인 오케스트레이터.
    
    각 Stage를 순차 실행하고, PipelineContext를 통해 데이터를 전달한다.
    Stage 모듈은 지연 초기화(Lazy Init)하여 서버 시작 시간을 최소화한다.
    모든 _run_<stage>()에 @stage_timer를 붙여 시간 측정/로깅/스냅샷을 자동화한다.
    """
    def __init__(self):
        self._stage_a = None
        self._stage_b = None
        self._initialized = False
    
    def _init_stages(self):
        """Stage 모듈 지연 초기화"""
        if self._initialized:
            return
        from pipeline.stages.stage_a.processor import StageAProcessor
        from pipeline.stages.stage_b.processor import StageBProcessor
        self._stage_a = StageAProcessor()
        self._stage_b = StageBProcessor()
        self._initialized = True
    
    def process(self, text: str, config: Optional[Dict] = None) -> PipelineContext:
        self._init_stages()
        ctx = PipelineContext(original_text=text, current_text=text, config=config or {})
        
        ctx = self._run_stage_a(ctx)    # Stage 1
        ctx = self._run_stage_b(ctx)    # Stage 2
        
        ctx.final_output = ctx.current_text
        return ctx
    
    @stage_timer("stage_a")
    def _run_stage_a(self, ctx: PipelineContext) -> PipelineContext:
        """순수 Stage 로직만 작성. 시간 측정/로깅/스냅샷은 데코레이터가 처리."""
        result = self._stage_a.process(ctx.current_text)
        ctx.current_text = result
        return ctx
    
    @stage_timer("stage_b")
    def _run_stage_b(self, ctx: PipelineContext) -> PipelineContext:
        result = self._stage_b.transform(ctx)
        ctx.current_text = result
        return ctx
```

**로그 출력 예시**:
```
[Pipeline] stage_a 완료: 3.2ms
[Pipeline] stage_b 완료: 1.8ms
[Pipeline] 전체 완료: 5.4ms
```

#### 3.5.3 Pipeline Context (Context Object 패턴)

Stage 간 데이터 전달 객체. 각 Stage가 읽고 쓰며, 모든 중간 결과와 스냅샷을 보관한다.

```python
# pipeline/pipeline_context.py
@dataclass
class StageSnapshot:
    """단일 Stage의 실행 스냅샷 — 디버깅 및 추적용"""
    stage_name: str
    input_text: str
    output_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

@dataclass
class PipelineContext:
    """
    파이프라인 전체 컨텍스트.
    
    - original_text: 원본 입력 (불변)
    - current_text: 현재 처리 중인 텍스트 (각 Stage가 업데이트)
    - snapshots: Stage별 스냅샷 (처리 과정 추적)
    - config: 처리 설정
    """
    original_text: str = ""
    current_text: str = ""
    snapshots: Dict[str, StageSnapshot] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    final_output: str = ""
    total_duration_ms: float = 0.0
    
    def add_snapshot(self, stage_name: str, snapshot: StageSnapshot):
        self.snapshots[stage_name] = snapshot
    
    def to_dict(self) -> Dict[str, Any]:
        """API 응답용 딕셔너리 변환"""
        ...
```

#### 3.5.4 Stage 모듈

각 Stage는 독립적인 처리 단위. **단일 책임 원칙**을 따르며, Context를 입력받아 수정 후 반환한다.

```
pipeline/stages/
├── stage_a/
│   ├── processor_a1.py     # 세부 처리기
│   ├── processor_a2.py
│   └── merger.py           # 결과 병합
├── stage_b/
│   ├── converter.py
│   └── transformer.py
└── ...
```

**Stage 규칙**:
- 입력: `PipelineContext` → 출력: 수정된 `PipelineContext`
- Stage 내부에서 다른 Stage를 직접 호출하지 않는다.
- Stage 간 데이터 공유는 반드시 Context를 통해서만 한다.
- `_run_<stage>()` 메서드에는 반드시 `@stage_timer("stage_name")`를 붙인다 — 스냅샷/로깅은 데코레이터가 자동 처리하므로 메서드 내부에서 직접 하지 않는다.

---

### 3.6 Workers 레이어 (`workers/` + `core/celery.py`) — 선택적

**역할**: Celery 기반 비동기 작업의 진입점. Beat 스케줄(주기적 작업)과 On-Demand 태스크를 정의한다.

**Workers는 API와 동급**이다 — 둘 다 "얇은 진입점"이며, 내부적으로 Service/Pipeline을 호출한다.

**규칙**:
- Workers에 비즈니스 로직을 넣지 않는다. Pipeline/Service 호출만 담당한다.
- `core/celery.py`에 Celery 앱 설정 + Beat 스케줄을 정의한다.
- `workers/tasks.py`에 태스크를 정의한다.
- 태스크 함수는 짧게, 실제 로직은 `_execute_<task>()` 헬퍼로 분리한다.
- Redis Lock으로 중복 실행을 방지한다 (`run_with_lock` 패턴).
- Beat 스케줄의 `task` 이름과 `@celery_app.task(name=...)` 이름이 반드시 일치해야 한다.

#### 3.6.1 Celery 앱 설정 (`core/celery.py`)

```python
# core/celery.py
from celery import Celery
from celery.schedules import crontab
from core.config import settings

celery_app = Celery(
    "my_service",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND_URL,
)

celery_app.conf.update(
    timezone="Asia/Seoul",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    imports=["workers.tasks"],
)

# Beat 스케줄 (주기적 작업)
# task 이름은 workers/tasks.py의 @celery_app.task(name=...) 과 반드시 일치
celery_app.conf.beat_schedule = {
    "example-hourly": {
        "task": "workers.tasks.task_example",
        "schedule": crontab(minute="0"),    # 매시 정각
    },
    "example-daily": {
        "task": "workers.tasks.task_daily_job",
        "schedule": crontab(hour="9", minute="0"),  # 매일 9시
    },
}
```

#### 3.6.2 태스크 정의 (`workers/tasks.py`)

```python
# workers/tasks.py
from core.celery import celery_app
from utils.redis_helper import get_redis_client, acquire_lock, release_lock

LOCK_EXPIRE = {
    "example": 3600,       # 1시간
    "daily_job": 7200,     # 2시간
}

def run_with_lock(task_name: str, func, *args, **kwargs):
    """Redis Lock으로 태스크 중복 실행 방지"""
    lock_key = f"lock:{task_name}"
    expire_time = LOCK_EXPIRE.get(task_name, 3600)
    
    redis_client = get_redis_client()
    if redis_client and not acquire_lock(redis_client, lock_key, expire=expire_time):
        logger.warning(f"[{task_name}] Skipped - lock held")
        return {"status": "skipped", "reason": "locked"}
    
    try:
        logger.info(f"[{task_name}] Starting...")
        result = func(*args, **kwargs)
        logger.info(f"[{task_name}] Completed")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"[{task_name}] Failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if redis_client:
            release_lock(redis_client, lock_key)


# --- 태스크 정의 ---
# 패턴: @celery_app.task → run_with_lock → _execute 헬퍼

@celery_app.task(name="workers.tasks.task_example")
def task_example():
    """매시 정각 실행되는 주기적 작업"""
    return run_with_lock("example", _execute_example)

def _execute_example():
    """실제 로직 — Pipeline/Service를 호출한다"""
    from pipeline.crawler import CrawlerPipeline, CrawlerState
    pipeline = CrawlerPipeline(stages=[...])
    state = pipeline.run(CrawlerState())
    return state.execution_summary

@celery_app.task(name="workers.tasks.task_deep_analysis")
def task_deep_analysis(stock_code: str):
    """On-Demand 태스크 — API에서 .delay()로 호출"""
    from services.analysis_service import analysis_service
    return analysis_service.analyze(stock_code)
```

#### 3.6.3 태스크 구조 패턴

```
@celery_app.task           ← 얇은 진입점 (인자 검증만)
    ↓
run_with_lock()            ← 중복 실행 방지 + 로깅 + 에러 래핑
    ↓
_execute_<task>()          ← 실제 로직 (Pipeline/Service 호출)
    ↓
Pipeline / Service         ← 비즈니스 로직 수행
```

**태스크 유형**:
| 유형 | 트리거 | 예시 |
|------|--------|------|
| **Beat (주기적)** | crontab 스케줄 | 데이터 수집, 동기화, 정리 작업 |
| **On-Demand (요청)** | `.delay()` / `.apply_async()` | 심층 분석, 리포트 생성 |

**실행 방법**:
```bash
# Worker 실행
celery -A core.celery worker --loglevel=info

# Beat 실행 (주기적 스케줄)
celery -A core.celery beat --loglevel=info

# Worker + Beat 동시 (개발용)
celery -A core.celery worker --beat --loglevel=info
```

---

### 3.7 DB 레이어 (`db/`)

**역할**: 데이터 영속성을 담당한다. **3단 분리**(Model → Repository → Service)로 구성한다.

#### 3.7.1 전체 구조

```
db/
├── database.py              # 엔진/세션 관리 (인프라)
├── base/
│   ├── base_repository.py   # Generic CRUD (데이터 접근)
│   └── base_service.py      # 트랜잭션 관리 (비즈니스 래퍼)
├── models/                  # ORM 모델 정의
├── repositories/            # 도메인별 레포지토리
└── services/                # 도메인별 DB 서비스
```

#### 3.7.2 database.py — 엔진/세션 관리

```python
# db/database.py
Base = declarative_base()

_engine = None
_SessionLocal = None

def get_engine():
    """SQLAlchemy 엔진 싱글톤 — 지연 초기화"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=3,
            max_overflow=5,
            pool_pre_ping=True,
        )
    return _engine

@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """DB 세션 컨텍스트 매니저 — with문으로 사용"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """스키마 + 테이블 자동 생성 (서버 시작 시 lifespan에서 호출)"""
    ...
```

#### 3.7.3 Base Repository — Generic CRUD

모든 도메인 레포지토리가 상속하는 **제네릭 베이스**. CRUD, Upsert, Bulk 연산을 공통으로 제공한다.

```python
# db/base/base_repository.py
class BaseRepository(Generic[T]):
    """
    공통 CRUD 레포지토리.
    
    - create / get_by_id / update / delete_obj
    - bulk_create / bulk_upsert
    - get_obj_by_keys / get_all_objs_by_keys (동적 필터)
    """
    def __init__(self, db: Session, model: type):
        self.db = db
        self.model = model
    
    def create(self, obj_data: Dict[str, Any]) -> T: ...
    def get_by_id(self, obj_id: Any) -> Optional[T]: ...
    def update(self, obj_id: Any, update_data: Dict[str, Any]) -> Optional[T]: ...
    def bulk_upsert(self, objs: List[Dict], unique_fields: List[str]) -> int: ...
```

#### 3.7.4 Base Service — 트랜잭션 관리

Repository를 래핑하여 **트랜잭션 경계**를 관리한다. 모든 쓰기 연산은 트랜잭션 내에서 실행된다.

```python
# db/base/base_service.py
class BaseService(Generic[T]):
    """
    트랜잭션 컨텍스트 관리 + CRUD 래퍼.
    
    - 모든 쓰기 연산을 transaction() 컨텍스트 내에서 실행
    - 실패 시 자동 rollback
    """
    def __init__(self, repository: BaseRepository[T], db_session: Session):
        self.repository = repository
        self.db = db_session
    
    @contextmanager
    def transaction(self):
        try:
            yield
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
    
    def create(self, obj_data: Dict) -> T:
        with self.transaction():
            return self.repository.create(obj_data)
```

#### 3.7.5 도메인 확장 패턴

새로운 도메인 엔티티를 추가할 때의 표준 절차:

```python
# 1. ORM 모델 정의
# db/models/feedback_model.py
class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = {'schema': settings.DB_SCHEMA}
    id = Column(Integer, primary_key=True)
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())

# 2. 도메인 레포지토리 (BaseRepository 상속 + 도메인 특화 쿼리)
# db/repositories/feedback_repository.py
class FeedbackRepository(BaseRepository[Feedback]):
    def __init__(self, db: Session):
        super().__init__(db, Feedback)
    
    def get_recent(self, limit: int) -> List[Feedback]:
        """도메인 특화 쿼리 — 최근 피드백 조회"""
        return self.db.query(self.model)\
            .order_by(self.model.created_at.desc())\
            .limit(limit).all()

# 3. 도메인 DB 서비스 (BaseService 상속 + 비즈니스 로직)
# db/services/feedback_service.py
class FeedbackService(BaseService[Feedback]):
    def __init__(self, db: Session):
        repo = FeedbackRepository(db)
        super().__init__(repo, db)
        self.feedback_repo = repo
    
    def save_feedback(self, data: Dict) -> Optional[Feedback]:
        """비즈니스 로직 포함된 저장 — 검증 + 트랜잭션"""
        with self.transaction():
            return self.feedback_repo.create(data)
```

---

## 4. 공통 디자인 패턴

### 4.1 설정 관리 — Pydantic Settings

```python
# core/config.py
class Settings(BaseSettings):
    """
    환경변수 기반 설정.
    .env 파일 자동 로드, 타입 검증, 기본값 제공.
    """
    PROJECT_NAME: str = "MyService"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # DB
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

**규칙**:
- 모든 설정은 환경변수로 주입한다 (하드코딩 금지).
- `@lru_cache()`로 싱글톤 보장.
- 파생 값은 `@property`로 정의한다.
- 모든 레이어에서 `from core.config import settings`로 참조한다.

---

### 4.2 엔트리포인트 — Lifespan 패턴

```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작/종료 시 실행되는 생명주기 관리.
    
    시작 시:
    1. DB 초기화 (스키마/테이블 생성)
    2. 모델/리소스 로드
    3. 웜업 (첫 추론 지연 제거)
    4. 백그라운드 태스크 시작
    
    종료 시:
    1. 스케줄러 중지
    2. 클라이언트 리소스 정리
    3. gRPC 서버 종료
    """
    # --- 시작 ---
    init_db()
    domain_service.load_resources()
    scheduler.start()
    yield
    # --- 종료 ---
    scheduler.stop()
    await livekit_client.close()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# 라우터 등록
app.include_router(domain_router, prefix=f"{settings.API_V1_STR}/domain", tags=["Domain"])
```

---

### 4.3 DTO 변환 흐름

외부 스키마(Pydantic)와 내부 객체(dataclass/Dict)를 명확히 분리한다.

```
[클라이언트 요청]
    ↓
Pydantic Schema (api/schemas/)       ← 외부 계약
    ↓  변환
Service DTO / Dict (services/)       ← 내부 표현
    ↓  변환
PipelineContext (pipeline/)           ← 파이프라인 내부
    ↓  변환
ORM Model (db/models/)               ← 영속성
```

**규칙**:
- API 스키마가 DB 모델을 직접 참조하지 않는다.
- 변환 로직은 각 경계(API↔Service, Service↔DB)에서 명시적으로 수행한다.

---

### 4.4 에러 처리 전략

| 레이어 | 전략 | 예시 |
|--------|------|------|
| **API** | `HTTPException`으로 변환 | `raise HTTPException(status_code=404, detail="...")` |
| **Service** | 도메인 예외 발생 또는 None 반환 | `raise DomainError("...")` |
| **Pipeline** | Stage 내부에서 처리, Fallback 적용 | `except: return fallback_result` |
| **DB** | 트랜잭션 rollback + 재발생 | `self.db.rollback(); raise` |
| **Client** | 재시도 + 타임아웃 + 래핑 | `raise ExternalServiceError(...)` |

**Fire-and-Forget 패턴** (로깅 등 부가 기능이 메인 흐름에 영향을 주지 않아야 할 때):
```python
try:
    feedback_logger.log(ctx)
except Exception:
    pass  # 실패해도 메인 처리에 영향 없음
```

---

### 4.5 지연 초기화 (Lazy Initialization)

무거운 리소스(ML 모델, 외부 연결 등)는 최초 사용 시점에 초기화한다.

```python
class PipelineOrchestrator:
    def __init__(self):
        self._stages = None
        self._initialized = False
    
    def _init_stages(self):
        if self._initialized:
            return
        # 무거운 import / 초기화
        from pipeline.stages.detection import Detector
        self._stages = {"detector": Detector()}
        self._initialized = True
    
    def process(self, text: str, config: Dict) -> PipelineContext:
        self._init_stages()  # 최초 호출 시에만 초기화
        ...
```

---

## 5. 레이어별 배치 기준 요약

| 모듈 성격 | 배치 위치 | 예시 |
|-----------|----------|------|
| REST/WS/gRPC 라우터 | `api/endpoints/` | `itn_endpoints.py` |
| 요청/응답 스키마 | `api/schemas/` | `itn_schemas.py` |
| 비즈니스 로직 서비스 | `services/` | `itn_service.py` |
| 서비스 간 전달 DTO | `services/` | `stream_dto.py` |
| **싱글톤 매니저** | **`managers/`** | `session_manager.py`, `scheduler.py` |
| **외부 API 클라이언트** | **`clients/`** | `livekit_client.py`, `stt_client.py` |
| 파이프라인 오케스트레이터 | `pipeline/` | `pipeline_orchestrator.py` |
| 파이프라인 컨텍스트 | `pipeline/` | `pipeline_context.py` |
| 파이프라인 데코레이터 | `pipeline/` | `decorators.py` (`@stage_timer`) |
| 파이프라인 처리 단계 | `pipeline/stages/` | `detection/`, `transformation/` |
| **Celery 앱 설정** | **`core/celery.py`** | Beat 스케줄 + 앱 설정 |
| **Celery 태스크** | **`workers/tasks.py`** | 태스크 정의 + `run_with_lock` |
| DB 엔진/세션 관리 | `db/database.py` | |
| Generic CRUD | `db/base/` | `base_repository.py` |
| ORM 모델 | `db/models/` | `feedback_model.py` |
| 도메인 레포지토리 | `db/repositories/` | `feedback_repository.py` |
| 도메인 DB 서비스 | `db/services/` | `feedback_service.py` |
| 환경 설정 | `core/config.py` | |
| 앱 엔트리포인트 | `main.py` | |

---

## 6. 새 프로젝트/도메인 추가 시 체크리스트

### 6.1 신규 프로젝트 시작

- [ ] `core/config.py` — Pydantic Settings 정의
- [ ] `main.py` — FastAPI + lifespan 구성
- [ ] `api/endpoints/` — 최소 1개 라우터 + health 엔드포인트
- [ ] `api/schemas/` — 요청/응답 스키마
- [ ] `services/` — 메인 도메인 서비스
- [ ] `managers/` — 필요한 싱글톤 매니저 배치
- [ ] `clients/` — 외부 API 호출 시 클라이언트 작성
- [ ] `db/` — DB 사용 시 database.py + base/ 구성
- [ ] `pipeline/` — 다단계 처리 필요 시 Orchestrator + Context + Stages 구성
- [ ] `workers/` — 비동기 작업 필요 시 `core/celery.py` + `workers/tasks.py` 구성
- [ ] `.env` — 환경변수 파일

### 6.2 신규 도메인 엔티티 추가 (DB)

- [ ] `db/models/<domain>_model.py` — ORM 모델 정의
- [ ] `db/repositories/<domain>_repository.py` — BaseRepository 상속 + 도메인 쿼리
- [ ] `db/services/<domain>_service.py` — BaseService 상속 + 비즈니스 로직
- [ ] `db/database.py`의 `init_db()`에 모델 import 추가

### 6.3 신규 파이프라인 Stage 추가

- [ ] `pipeline/stages/<stage_name>/` 디렉토리 생성
- [ ] Stage 처리기 클래스 작성 (입력: Context → 출력: Context)
- [ ] `pipeline_orchestrator.py`에 Stage 등록 + `_init_stages()`에 import 추가
- [ ] `PipelineContext`에 필요한 필드 추가 (해당 시)

### 6.4 신규 외부 API 연동

- [ ] `clients/base_client.py` 존재 확인 (없으면 생성)
- [ ] `clients/<external>_client.py` — BaseClient 상속 + 메서드 정의
- [ ] `core/config.py`에 외부 서비스 URL/키/타임아웃 설정 추가
- [ ] 서비스 레이어에서 client import하여 사용

---

## 7. 에이전트 지시사항 요약

> AI 에이전트가 코드를 작성할 때 반드시 따라야 하는 규칙:

1. **레이어 분리**: API → Service → Pipeline → DB 순서를 지키고, 역방향 참조하지 않는다.
2. **API 레이어는 얇게**: 스키마 변환 + 서비스 호출만 한다. 비즈니스 로직을 넣지 않는다.
3. **싱글톤은 `managers/`에**: 상태를 가지는 싱글톤 객체는 반드시 `managers/` 하위에 배치한다.
4. **외부 호출은 `clients/`에**: 외부 API/서비스 호출은 반드시 `clients/` 하위에 클라이언트 클래스로 작성한다.
5. **파이프라인 4요소**: Orchestrator + Context + Stages + `@stage_timer` 데코레이터. Stage는 독립적으로, Context를 통해서만 데이터를 공유한다. 모든 `_run_<stage>()`에는 반드시 `@stage_timer`를 붙인다.
6. **DB 3단 분리**: Model → Repository → Service. BaseRepository/BaseService를 상속한다.
7. **설정은 환경변수로**: `core/config.py`의 Pydantic Settings를 사용한다. 하드코딩 금지.
8. **DTO 경계 분리**: API 스키마 ↔ 서비스 DTO ↔ DB 모델을 명확히 분리하고, 각 경계에서 변환한다.
9. **에러 처리**: 각 레이어에 맞는 에러 전략을 적용한다. 메인 흐름에 영향을 주지 않는 부가 기능은 Fire-and-Forget.
10. **지연 초기화**: 무거운 리소스는 최초 사용 시점에 초기화한다.
11. **Workers는 API와 동급**: Celery 태스크는 `workers/tasks.py`에 정의하고, 비즈니스 로직을 넣지 않는다. `@task → run_with_lock → _execute → Pipeline/Service` 패턴을 따른다. Beat 스케줄은 `core/celery.py`에 정의한다.
