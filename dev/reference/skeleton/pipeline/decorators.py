"""
파이프라인 데코레이터 — Stage 실행 시간 로깅/스냅샷 자동화.

@stage_timer를 _run_<stage>() 메서드에 붙이면:
1. 실행 시간 측정
2. loguru로 Stage명 + 소요시간 자동 로깅
3. StageSnapshot 자동 생성 + Context에 추가

[사용법]
class PipelineOrchestrator:
    @stage_timer("detection")
    def _run_detection(self, ctx: PipelineContext) -> PipelineContext:
        # Stage 로직만 작성하면 된다. 시간 측정/로깅/스냅샷은 데코레이터가 처리.
        ctx.entities = self._detection["ner"].detect(ctx.current_text)
        return ctx
"""

import time
from functools import wraps
from typing import Callable
from loguru import logger

from pipeline.pipeline_context import PipelineContext, StageSnapshot


def stage_timer(stage_name: str):
    """
    Stage 실행 시간을 자동으로 측정·로깅·스냅샷하는 데코레이터.

    Args:
        stage_name: Stage 식별 이름 (스냅샷 키 및 로그에 사용)

    동작:
        1. ctx.current_text를 input_text로 캡처
        2. 래핑된 메서드 실행
        3. 실행 시간 측정 → logger.info 출력
        4. StageSnapshot 생성 → ctx.add_snapshot() 자동 호출
        5. 수정된 ctx 반환

    메서드가 반환하는 ctx.current_text와 input_text가 다르면
    스냅샷의 input/output에 각각 기록된다.
    """
    def decorator(func: Callable):
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
