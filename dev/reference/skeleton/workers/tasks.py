"""
Celery 태스크 정의 — Workers 레이어.

Workers는 API와 동급의 "얇은 진입점"이다.
비즈니스 로직을 넣지 않고, Pipeline/Service를 호출한다.

[태스크 작성 패턴]
    @celery_app.task           ← 얇은 진입점 (인자 검증만)
        ↓
    run_with_lock()            ← 중복 실행 방지 + 로깅 + 에러 래핑
        ↓
    _execute_<task>()          ← 실제 로직 (Pipeline/Service 호출)
        ↓
    Pipeline / Service         ← 비즈니스 로직 수행

[Beat 스케줄과 연동]
    - core/celery.py의 beat_schedule에 정의된 task 이름과
      @celery_app.task(name=...) 이름이 반드시 일치해야 함
    - 예: beat_schedule "task": "workers.tasks.task_example"
          ↔ @celery_app.task(name="workers.tasks.task_example")

[On-Demand 태스크 호출 (API에서)]
    from workers.tasks import task_deep_analysis
    task_deep_analysis.delay(stock_code="005930")
"""

from loguru import logger

from core.celery import celery_app


# Lock 만료 시간 (초) — 태스크별로 정의
LOCK_EXPIRE = {
    "example": 3600,       # 1시간
    "daily_job": 7200,     # 2시간
}


def run_with_lock(task_name: str, func, *args, **kwargs):
    """
    Redis Lock으로 태스크 중복 실행 방지.

    동일 태스크가 이미 실행 중이면 스킵한다.
    성공/실패/스킵 상태를 딕셔너리로 반환한다.
    """
    # Redis 유틸 import (프로젝트에 맞게 수정)
    # from utils.redis_helper import get_redis_client, acquire_lock, release_lock
    #
    # lock_key = f"lock:{task_name}"
    # expire_time = LOCK_EXPIRE.get(task_name, 3600)
    #
    # redis_client = get_redis_client()
    # if redis_client and not acquire_lock(redis_client, lock_key, expire=expire_time):
    #     logger.warning(f"[{task_name}] Skipped - lock held")
    #     return {"status": "skipped", "reason": "locked"}

    try:
        logger.info(f"[{task_name}] Starting...")
        result = func(*args, **kwargs)
        logger.info(f"[{task_name}] Completed")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"[{task_name}] Failed: {e}")
        return {"status": "error", "error": str(e)}
    # finally:
    #     if redis_client:
    #         release_lock(redis_client, lock_key)


# ============================================================================
# Beat 태스크 (주기적 작업)
# ============================================================================

# @celery_app.task(name="workers.tasks.task_example")
# def task_example():
#     """매시 정각 실행되는 주기적 작업"""
#     return run_with_lock("example", _execute_example)
#
# def _execute_example():
#     """실제 로직 — Pipeline을 호출한다"""
#     from pipeline.example import ExamplePipeline, ExampleState
#     pipeline = ExamplePipeline(stages=[...])
#     state = pipeline.run(ExampleState())
#     return state.execution_summary


# ============================================================================
# On-Demand 태스크 (API에서 .delay()로 호출)
# ============================================================================

# @celery_app.task(name="workers.tasks.task_deep_analysis")
# def task_deep_analysis(item_id: str):
#     """특정 항목 심층 분석 — API에서 요청 시 비동기 실행"""
#     from services.analysis_service import analysis_service
#     return analysis_service.analyze(item_id)
