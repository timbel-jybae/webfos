"""
파이프라인 오케스트레이터 — 다단계 처리 흐름을 제어하는 지휘자.

[구조]
- _init_stages(): Stage 모듈 지연 초기화 (Lazy Init)
- process(): 전체 파이프라인 실행 (Context 생성 → Stage 순차 실행 → 반환)
- _run_<stage>(): 개별 Stage 실행 (@stage_timer 데코레이터로 시간 측정 자동화)

[확장 시]
1. stages/ 하위에 새 Stage 디렉토리를 생성한다.
2. _init_stages()에 import를 추가한다.
3. _run_<stage>() 메서드를 작성하고 @stage_timer("stage_name")를 붙인다.
4. process()에 _run_<stage>() 호출을 추가한다.
5. 조건부 실행이 필요하면 config 값으로 분기한다.
"""

import time
from typing import Dict, Any, Optional
from loguru import logger

from core.config import settings
from pipeline.pipeline_context import PipelineContext, StageSnapshot
from pipeline.decorators import stage_timer


class PipelineOrchestrator:
    """
    N단계 파이프라인 오케스트레이터.

    각 Stage를 순차 실행하고, PipelineContext를 통해 데이터를 전달한다.
    Stage 모듈은 지연 초기화하여 서버 시작 시간을 최소화한다.

    모든 _run_<stage>() 메서드에 @stage_timer를 붙여
    실행 시간 로깅 + 스냅샷 기록을 자동화한다.
    """

    def __init__(self):
        # Stage 모듈 (지연 초기화)
        self._stage_a = None
        self._stage_b = None
        self._initialized = False

    def _init_stages(self):
        """
        Stage 모듈 지연 초기화.
        무거운 import(ML 모델 등)를 최초 호출 시점으로 지연시킨다.
        """
        if self._initialized:
            return

        # [확장 시] 여기에 Stage import를 추가한다.
        # from pipeline.stages.stage_a.processor import StageAProcessor
        # from pipeline.stages.stage_b.processor import StageBProcessor
        # self._stage_a = StageAProcessor()
        # self._stage_b = StageBProcessor()

        self._initialized = True
        logger.info("파이프라인 Stage 초기화 완료")

    def process(self, text: str, config: Optional[Dict] = None) -> PipelineContext:
        """
        전체 파이프라인 실행.

        1. Context 생성
        2. Stage별 순차 실행 (config에 따라 조건부 스킵 가능)
        3. 각 Stage 완료 시 @stage_timer가 자동으로 스냅샷 기록
        4. 최종 Context 반환
        """
        self._init_stages()

        start_time = time.time()

        ctx = PipelineContext(
            original_text=text,
            current_text=text,
            config=config or {},
        )

        # Stage 순차 실행
        # ctx = self._run_stage_a(ctx)
        # ctx = self._run_stage_b(ctx)

        # 조건부 실행 예시:
        # if settings.SOME_FEATURE_ENABLED:
        #     ctx = self._run_stage_c(ctx)

        ctx.final_output = ctx.current_text
        ctx.total_duration_ms = (time.time() - start_time) * 1000

        logger.info(f"[Pipeline] 전체 완료: {ctx.total_duration_ms:.1f}ms")

        return ctx

    # === 개별 Stage 실행 메서드 ===
    # @stage_timer가 자동으로:
    #   - 실행 시간 측정 + 로깅
    #   - StageSnapshot 생성 + ctx에 추가
    # 따라서 메서드 내부에는 순수 Stage 로직만 작성하면 된다.

    # @stage_timer("stage_a")
    # def _run_stage_a(self, ctx: PipelineContext) -> PipelineContext:
    #     result = self._stage_a.process(ctx.current_text)
    #     ctx.current_text = result
    #     return ctx

    # @stage_timer("stage_b")
    # def _run_stage_b(self, ctx: PipelineContext) -> PipelineContext:
    #     result = self._stage_b.transform(ctx)
    #     ctx.current_text = result
    #     return ctx
