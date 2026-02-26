"""
턴 관리 데이터 모델.

속기사들의 작업 턴을 관리하기 위한 데이터 구조를 정의한다.
"""

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class TurnState(Enum):
    """
    턴 상태
    
    - IDLE: 대기 상태 (아직 시작되지 않음)
    - ACTIVE: 활성 상태 (현재 작업 진행 중)
    - TRANSITIONING: 전환 중 (현재 턴 종료, 다음 턴 시작 사이)
    - COMPLETED: 완료됨
    """
    IDLE = "idle"
    ACTIVE = "active"
    TRANSITIONING = "transitioning"
    COMPLETED = "completed"


@dataclass
class Turn:
    """
    턴 정보
    
    속기사의 작업 턴을 나타내는 데이터 클래스.
    각 턴은 고유 ID를 가지며, 특정 속기사에게 할당된다.
    
    Attributes:
        id: 턴 고유 ID (UUID)
        holder_identity: 현재 권한 보유 속기사 identity
        start_timestamp_ms: 턴 시작 영상 타임스탬프 (밀리초)
        end_timestamp_ms: 턴 종료 영상 타임스탬프 (밀리초, 종료 시 설정)
        state: 턴 상태
        segment_ids: 해당 턴에서 작성된 자막 세그먼트 ID 목록
        created_at: 턴 생성 시각 (서버 시간)
        updated_at: 턴 수정 시각 (서버 시간)
    """
    holder_identity: str
    start_timestamp_ms: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    end_timestamp_ms: Optional[int] = None
    state: TurnState = TurnState.IDLE
    segment_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def start(self) -> "Turn":
        """
        턴 시작
        
        Returns:
            self (체이닝 지원)
        """
        self.state = TurnState.ACTIVE
        self.updated_at = datetime.now()
        return self
    
    def end(self, end_timestamp_ms: int) -> "Turn":
        """
        턴 종료
        
        Args:
            end_timestamp_ms: 종료 영상 타임스탬프
            
        Returns:
            self (체이닝 지원)
        """
        self.end_timestamp_ms = end_timestamp_ms
        self.state = TurnState.COMPLETED
        self.updated_at = datetime.now()
        return self
    
    def add_segment(self, segment_id: str) -> "Turn":
        """
        자막 세그먼트 ID 추가
        
        Args:
            segment_id: 추가할 세그먼트 ID
            
        Returns:
            self (체이닝 지원)
        """
        if segment_id not in self.segment_ids:
            self.segment_ids.append(segment_id)
            self.updated_at = datetime.now()
        return self
    
    def is_active(self) -> bool:
        """턴이 활성 상태인지 확인"""
        return self.state == TurnState.ACTIVE
    
    def duration_ms(self) -> Optional[int]:
        """
        턴 지속 시간 (밀리초)
        
        Returns:
            지속 시간, 종료되지 않았으면 None
        """
        if self.end_timestamp_ms is None:
            return None
        return self.end_timestamp_ms - self.start_timestamp_ms
    
    def to_dict(self) -> dict:
        """딕셔너리 변환 (직렬화용)"""
        return {
            "id": self.id,
            "holder_identity": self.holder_identity,
            "start_timestamp_ms": self.start_timestamp_ms,
            "end_timestamp_ms": self.end_timestamp_ms,
            "state": self.state.value,
            "segment_ids": self.segment_ids,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Turn":
        """딕셔너리에서 생성 (역직렬화용)"""
        turn = cls(
            holder_identity=data["holder_identity"],
            start_timestamp_ms=data["start_timestamp_ms"],
            id=data.get("id", str(uuid.uuid4())),
            end_timestamp_ms=data.get("end_timestamp_ms"),
            state=TurnState(data.get("state", "idle")),
            segment_ids=data.get("segment_ids", []),
        )
        if "created_at" in data:
            turn.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            turn.updated_at = datetime.fromisoformat(data["updated_at"])
        return turn


@dataclass
class Participant:
    """
    참가자 정보
    
    Room에 참여한 속기사 또는 검수자 정보.
    
    Attributes:
        identity: 참가자 고유 ID
        role: 역할 ("stenographer" | "reviewer")
        name: 표시 이름
        is_active: 활성 상태 (연결됨)
        joined_at: 입장 시각
    """
    identity: str
    role: str
    name: str = ""
    is_active: bool = True
    joined_at: datetime = field(default_factory=datetime.now)
    
    def is_stenographer(self) -> bool:
        """속기사인지 확인"""
        return self.role == "stenographer"
    
    def is_reviewer(self) -> bool:
        """검수자인지 확인"""
        return self.role == "reviewer"
    
    def to_dict(self) -> dict:
        """딕셔너리 변환"""
        return {
            "identity": self.identity,
            "role": self.role,
            "name": self.name,
            "is_active": self.is_active,
            "joined_at": self.joined_at.isoformat(),
        }
