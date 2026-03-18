"""
RoomAgent 패키지.

실시간 자막 속기 시스템의 중앙 허브 역할을 수행하는 Agent 모듈.

[advice from AI] VideoRouter 제거 (클라이언트 측 버퍼링 사용)
[advice from AI] Phase 1-4 리팩토링으로 Handler 모듈 분리
"""

from .models import (
    Turn,
    TurnState,
    CaptionSegment,
    CaptionStatus,
    RoomMessage,
    MessageType,
)
from .turn_manager import TurnManager
from .caption_manager import CaptionManager, MergedCaption
from .external_connector import ExternalConnector
from .message_handler import MessageHandler
from .room_agent import RoomAgent, AgentState

# [advice from AI] 분리된 핸들러 모듈
from .stt_handler import STTHandler
from .participant_handler import ParticipantHandler
from .message_dispatcher import MessageDispatcher
from .frontend_handler import FrontendHandler

__all__ = [
    # 데이터 모델
    "Turn",
    "TurnState",
    "CaptionSegment",
    "CaptionStatus",
    "RoomMessage",
    "MessageType",
    # 턴 관리
    "TurnManager",
    # 자막 관리
    "CaptionManager",
    "MergedCaption",
    # 외부 연동
    "ExternalConnector",
    # 메시지 처리
    "MessageHandler",
    # 분리된 핸들러 (Phase 1-4 리팩토링)
    "STTHandler",
    "ParticipantHandler",
    "MessageDispatcher",
    "FrontendHandler",
    # RoomAgent
    "RoomAgent",
    "AgentState",
]
