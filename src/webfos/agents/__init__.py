"""
RoomAgent 패키지.

실시간 자막 속기 시스템의 중앙 허브 역할을 수행하는 Agent 모듈.
"""

from .models import (
    Turn,
    TurnState,
    CaptionSegment,
    CaptionStatus,
    RoomMessage,
    MessageType,
)
from .video_router import VideoRouter, FrameRingBuffer
from .turn_manager import TurnManager
from .caption_manager import CaptionManager, MergedCaption
from .external_connector import ExternalConnector
from .message_handler import MessageHandler
from .room_agent import RoomAgent, AgentState

__all__ = [
    # 데이터 모델
    "Turn",
    "TurnState",
    "CaptionSegment",
    "CaptionStatus",
    "RoomMessage",
    "MessageType",
    # 영상 라우팅
    "VideoRouter",
    "FrameRingBuffer",
    # 턴 관리
    "TurnManager",
    # 자막 관리
    "CaptionManager",
    "MergedCaption",
    # 외부 연동
    "ExternalConnector",
    # 메시지 처리
    "MessageHandler",
    # RoomAgent
    "RoomAgent",
    "AgentState",
]
