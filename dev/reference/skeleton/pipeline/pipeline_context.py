"""
파이프라인 컨텍스트 — Stage 간 데이터 전달 객체.

각 Stage가 읽고 쓰며, 최종 결과와 모든 중간 스냅샷을 보관한다.

[확장 시]
- 도메인에 필요한 필드를 PipelineContext에 추가한다.
- 필드 추가 시 to_dict()도 함께 업데이트한다.
- StageSnapshot은 그대로 재사용한다.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class StageSnapshot:
    """
    단일 Stage의 실행 스냅샷 — 디버깅 및 처리 과정 추적용.

    각 Stage 완료 시 Orchestrator가 생성하여 Context에 추가한다.
    """
    stage_name: str
    input_text: str
    output_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PipelineContext:
    """
    파이프라인 전체 컨텍스트.

    - original_text: 원본 입력 (불변, Stage에서 수정하지 않는다)
    - current_text: 현재 처리 중인 텍스트 (각 Stage가 업데이트)
    - snapshots: Stage별 스냅샷 (처리 과정 추적)
    - config: 처리 설정 (모드, 옵션 등)

    [도메인 확장 예시]
    entities: List[DetectedEntity] = field(default_factory=list)
    consistency_map: Dict[str, str] = field(default_factory=dict)
    """

    # 원본 (불변)
    original_text: str = ""

    # 현재 텍스트 (각 Stage가 업데이트)
    current_text: str = ""

    # Stage별 스냅샷 (추적용)
    snapshots: Dict[str, StageSnapshot] = field(default_factory=dict)

    # 처리 설정
    config: Dict[str, Any] = field(default_factory=dict)

    # 최종 출력
    final_output: str = ""

    # 전체 소요 시간
    total_duration_ms: float = 0.0

    def add_snapshot(self, stage_name: str, snapshot: StageSnapshot):
        """스냅샷 추가"""
        self.snapshots[stage_name] = snapshot

    def to_dict(self) -> Dict[str, Any]:
        """API 응답용 딕셔너리 변환"""
        return {
            "original": self.original_text,
            "final_output": self.final_output,
            "snapshots": {
                name: {
                    "input": s.input_text[:200],
                    "output": s.output_text[:200],
                    "duration_ms": s.duration_ms,
                    "metadata": s.metadata,
                }
                for name, s in self.snapshots.items()
            },
            "total_duration_ms": self.total_duration_ms,
        }
