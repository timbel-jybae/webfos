"""
RoomAgent 메인 클래스.

실시간 자막 속기 시스템의 중앙 허브 역할을 수행한다.
- 턴 관리 (TurnManager)
- 메시지 처리 (MessageHandler)
- 자막 관리 (CaptionManager)
- 외부 연동 (ExternalConnector)

[advice from AI] VideoRouter 제거 (클라이언트 측 버퍼링 사용)
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from enum import Enum

from loguru import logger

try:
    from livekit import rtc
except ImportError:
    rtc = None

from .turn_manager import TurnManager
from .message_handler import MessageHandler
from .caption_manager import CaptionManager, MergedCaption
from .external_connector import ExternalConnector
from .models.turn import Turn
from .models.caption import CaptionSegment, STTResult, OCRResult


class AgentState(Enum):
    """RoomAgent 상태"""
    INITIALIZING = "initializing"
    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


class RoomAgent:
    """
    RoomAgent 중앙 허브
    
    채널별 Room에서 자막/턴 관리를 담당하는 핵심 클래스.
    
    Attributes:
        room: LiveKit Room 인스턴스
        room_name: Room 이름
        state: Agent 상태
        turn_manager: 턴 관리 모듈
        caption_manager: 자막 관리 모듈
        external_connector: 외부 연동 모듈
        message_handler: DataChannel 메시지 처리기
    
    Example:
        agent = RoomAgent(
            delay_ms=3500,
            turn_duration_ms=30000,
        )
        await agent.start(room)
        ...
        await agent.stop()
    """
    
    INGRESS_IDENTITY = "ingress-hls-source"
    
    def __init__(
        self,
        delay_ms: int = 3500,
        turn_duration_ms: int = 30000,
        auto_switch: bool = False,
        max_stenographers: int = 4,
        caption_retention_ms: int = 60000,
        stt_url: str = "",
        stt_timeout: float = 5.0,
        ocr_url: str = "",
        ocr_timeout: float = 5.0,
        broadcast_url: str = "",
        broadcast_timeout: float = 10.0,
        agent_identity: str = "room-agent",
    ):
        """
        Args:
            delay_ms: 검수자용 영상 지연 시간 (밀리초, 클라이언트 측 참조용)
            turn_duration_ms: 기본 턴 지속 시간 (밀리초)
            auto_switch: 자동 턴 전환 활성화 여부
            max_stenographers: 최대 속기사 수
            caption_retention_ms: 자막 버퍼 보관 시간 (밀리초)
            stt_url: STT 서비스 URL (빈 문자열이면 비활성화)
            stt_timeout: STT 서비스 타임아웃 (초)
            ocr_url: OCR 서비스 URL (빈 문자열이면 비활성화)
            ocr_timeout: OCR 서비스 타임아웃 (초)
            broadcast_url: 방송국 전송 URL (빈 문자열이면 비활성화)
            broadcast_timeout: 방송국 전송 타임아웃 (초)
            agent_identity: Agent identity
        """
        self.room: Optional["rtc.Room"] = None
        self.room_name: str = ""
        self.state: AgentState = AgentState.INITIALIZING
        self.agent_identity = agent_identity
        self.delay_ms = delay_ms
        
        self._start_time_ms: int = 0
        
        self.turn_manager = TurnManager(
            turn_duration_ms=turn_duration_ms,
            auto_switch=auto_switch,
            max_stenographers=max_stenographers,
        )
        
        self.caption_manager = CaptionManager(
            retention_ms=caption_retention_ms,
        )
        
        self.external_connector = ExternalConnector(
            stt_url=stt_url,
            stt_timeout=stt_timeout,
            ocr_url=ocr_url,
            ocr_timeout=ocr_timeout,
            broadcast_url=broadcast_url,
            broadcast_timeout=broadcast_timeout,
        )
        
        self.message_handler = MessageHandler(
            agent_identity=agent_identity,
        )
        
        self._setup_turn_callbacks()
        self._setup_caption_callbacks()
        self._setup_external_callbacks()
        
        logger.info(
            f"[RoomAgent] 초기화: delay={delay_ms}ms, "
            f"turn_duration={turn_duration_ms}ms"
        )
    
    def _setup_turn_callbacks(self) -> None:
        """턴 관련 콜백 설정"""
        
        async def on_turn_start(turn: Turn) -> None:
            await self.message_handler.broadcast_turn_start(turn)
            if turn.holder_identity:
                await self.message_handler.send_turn_grant(
                    turn, turn.holder_identity
                )
        
        async def on_turn_end(turn: Turn) -> None:
            await self.message_handler.broadcast_turn_end(turn)
            self.caption_manager.merge_segments(turn.id)
        
        self.turn_manager.on_turn_start(on_turn_start)
        self.turn_manager.on_turn_end(on_turn_end)
    
    def _setup_caption_callbacks(self) -> None:
        """자막 관련 콜백 설정"""
        
        async def on_segment_submitted(segment: CaptionSegment) -> None:
            await self.message_handler.broadcast_caption_update(segment)
        
        self.caption_manager.on_segment_submitted(on_segment_submitted)
    
    def _setup_external_callbacks(self) -> None:
        """외부 연동 콜백 설정"""
        
        async def on_stt_result(result: STTResult) -> None:
            self.caption_manager.add_stt_result(result)
        
        async def on_ocr_result(result: OCRResult) -> None:
            self.caption_manager.add_ocr_result(result)
        
        self.external_connector.on_stt_result(on_stt_result)
        self.external_connector.on_ocr_result(on_ocr_result)
    
    async def start(
        self,
        room: "rtc.Room",
    ) -> None:
        """
        RoomAgent 시작
        
        Args:
            room: LiveKit Room 인스턴스
        """
        self.room = room
        self.room_name = room.name
        self.state = AgentState.READY
        self._start_time_ms = int(time.time() * 1000)
        
        logger.info(f"[RoomAgent] 시작: room={self.room_name}")
        
        await self.caption_manager.start()
        await self.external_connector.start()
        
        await self.message_handler.start(
            room=room,
            turn_manager=self.turn_manager,
            caption_manager=self.caption_manager,
        )
        
        self._setup_event_handlers()
        self._check_existing_participants()
        
        self.state = AgentState.ACTIVE
    
    def _setup_event_handlers(self) -> None:
        """Room 이벤트 핸들러 설정"""
        
        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track: "rtc.Track",
            publication: "rtc.RemoteTrackPublication",
            participant: "rtc.RemoteParticipant",
        ):
            logger.info(
                f"[RoomAgent] 트랙 구독: {participant.identity} "
                f"{track.kind} (room={self.room_name})"
            )
        
        @self.room.on("track_unsubscribed")
        def on_track_unsubscribed(
            track: "rtc.Track",
            publication: "rtc.RemoteTrackPublication",
            participant: "rtc.RemoteParticipant",
        ):
            logger.info(
                f"[RoomAgent] 트랙 구독 해제: {participant.identity} "
                f"{track.kind} (room={self.room_name})"
            )
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: "rtc.RemoteParticipant"):
            logger.info(
                f"[RoomAgent] 참가자 입장: {participant.identity} "
                f"(room={self.room_name})"
            )
            asyncio.create_task(
                self._register_participant(participant)
            )
        
        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: "rtc.RemoteParticipant"):
            logger.info(
                f"[RoomAgent] 참가자 퇴장: {participant.identity} "
                f"(room={self.room_name})"
            )
            asyncio.create_task(
                self._unregister_participant(participant)
            )
    
    def _check_existing_participants(self) -> None:
        """기존 참가자 확인 (Agent가 나중에 입장한 경우)"""
        for participant in self.room.remote_participants.values():
            logger.info(
                f"[RoomAgent] 기존 참가자 확인: {participant.identity}"
            )
            asyncio.create_task(self._register_participant(participant))
    
    async def _register_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        참가자 등록
        
        participant metadata에서 role 정보를 추출하여 TurnManager에 등록한다.
        metadata 형식: {"role": "stenographer" | "reviewer", "name": "..."}
        """
        identity = participant.identity
        
        if identity == self.INGRESS_IDENTITY:
            return
        
        role = "stenographer"
        name = identity
        
        if participant.metadata:
            try:
                import json
                meta = json.loads(participant.metadata)
                role = meta.get("role", "stenographer")
                name = meta.get("name", identity)
            except (json.JSONDecodeError, TypeError):
                pass
        
        success = self.turn_manager.register_participant(identity, role, name)
        if success:
            logger.info(
                f"[RoomAgent] 참가자 등록 완료: {identity} ({role})"
            )
    
    async def _unregister_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """참가자 등록 해제"""
        identity = participant.identity
        
        if identity == self.INGRESS_IDENTITY:
            return
        
        if self.turn_manager.get_current_holder() == identity:
            current_ts = self.get_current_timestamp()
            await self.turn_manager.switch_turn(None, current_ts)
        
        self.turn_manager.unregister_participant(identity)
    
    async def start_turn(self, holder_identity: str) -> Optional[Turn]:
        """
        턴 시작 (API)
        
        지정된 속기사에게 턴 권한을 부여한다.
        
        Args:
            holder_identity: 속기사 identity
            
        Returns:
            생성된 Turn 객체
        """
        current_ts = self.get_current_timestamp()
        return await self.turn_manager.start_turn(holder_identity, current_ts)
    
    async def switch_turn(
        self,
        next_holder: Optional[str] = None,
    ) -> bool:
        """
        턴 전환 (API)
        
        Args:
            next_holder: 다음 턴 보유자 (None이면 자동 선택)
            
        Returns:
            성공 여부
        """
        current_ts = self.get_current_timestamp()
        result = await self.turn_manager.switch_turn(next_holder, current_ts)
        return result.success
    
    def has_turn_permission(self, identity: str) -> bool:
        """턴 권한 확인"""
        return self.turn_manager.has_permission(identity)
    
    async def stop(self) -> None:
        """RoomAgent 중지 및 리소스 정리"""
        logger.info(f"[RoomAgent] 중지: room={self.room_name}")
        
        self.state = AgentState.SHUTTING_DOWN
        
        await self.message_handler.stop()
        await self.turn_manager.stop()
        await self.caption_manager.stop()
        await self.external_connector.stop()
        
        self.room = None
        
        logger.info("[RoomAgent] 리소스 정리 완료")
    
    def get_current_timestamp(self) -> int:
        """현재 영상 타임스탬프 (밀리초)"""
        return int(time.time() * 1000) - self._start_time_ms
    
    def get_delayed_timestamp(self) -> int:
        """지연된 영상 타임스탬프 (밀리초)"""
        return max(0, self.get_current_timestamp() - self.delay_ms)
    
    def get_captions_in_range(
        self,
        start_ms: int,
        end_ms: int,
    ) -> List[CaptionSegment]:
        """시간 범위 내 자막 조회"""
        return self.caption_manager.get_segments_in_range(start_ms, end_ms)
    
    def get_merged_caption(self, turn_id: str) -> Optional[MergedCaption]:
        """병합된 자막 조회"""
        return self.caption_manager.get_merged_caption(turn_id)
    
    async def send_caption_to_broadcast(
        self,
        caption_text: str,
        timestamp_ms: int,
    ) -> bool:
        """방송국에 자막 전송"""
        return await self.external_connector.send_caption_to_broadcast(
            caption_text=caption_text,
            timestamp_ms=timestamp_ms,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Agent 상태 정보"""
        return {
            "room_name": self.room_name,
            "state": self.state.value,
            "agent_identity": self.agent_identity,
            "delay_ms": self.delay_ms,
            "turn_manager": self.turn_manager.get_stats(),
            "caption_manager": self.caption_manager.get_stats(),
            "external_connector": self.external_connector.get_stats(),
        }
