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
from .stt_handler import STTHandler
from .participant_handler import ParticipantHandler
from .message_dispatcher import MessageDispatcher
from .frontend_handler import FrontendHandler
from .models.turn import Turn
from .models.caption import CaptionSegment, STTResult, OCRResult

# [advice from AI] Redis 클라이언트 (상태 공유용)
try:
    from clients.redis_client import redis_client
except ImportError:
    redis_client = None

# [advice from AI] STT 연결 (조건부 import - 크래시 방지)
STTConnector = None

from core.config import settings


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
        
        # [advice from AI] 속기사별 텍스트 상태 및 송출 텍스트 중앙 관리
        self._stenographer_texts: Dict[str, str] = {}  # identity -> 현재 입력 텍스트
        self._broadcast_text: str = ""  # 현재 송출된 텍스트
        
        # [advice from AI] STT 처리 핸들러 (Phase 1 리팩토링)
        self.stt_handler = STTHandler(
            get_current_holder=lambda: self.turn_manager.get_current_holder(),
            send_to_participant=self._send_to_participant,
            get_current_timestamp=self.get_current_timestamp,
        )
        
        # [advice from AI] Ingress 오디오 트랙 관련 (STTHandler 외부 관리)
        self._has_ingress_audio: bool = False
        self._stt_stream_task: Optional[asyncio.Task] = None
        
        # [advice from AI] 메시지 전송 핸들러 (Phase 3 리팩토링)
        self.message_dispatcher = MessageDispatcher(
            get_room=lambda: self.room,
            get_room_name=lambda: self.room_name,
            turn_manager=self.turn_manager,
            get_stenographer_texts=lambda: self._stenographer_texts,
            get_broadcast_text=lambda: self._broadcast_text,
        )
        
        # [advice from AI] 참가자 관리 핸들러 (Phase 2 리팩토링)
        self.participant_handler = ParticipantHandler(
            turn_manager=self.turn_manager,
            get_stenographer_texts=lambda: self._stenographer_texts,
            set_stenographer_text=lambda k, v: self._stenographer_texts.__setitem__(k, v),
            remove_stenographer_text=lambda k: self._stenographer_texts.pop(k, None),
            send_raw_message=self._send_raw_message,
            broadcast_turn_state=self._broadcast_turn_state,
            start_turn=self.start_turn,
            get_current_timestamp=self.get_current_timestamp,
            get_broadcast_text=lambda: self._broadcast_text,
            set_broadcast_text=lambda v: setattr(self, '_broadcast_text', v),
            stop_stt=self.stop_stt,
            get_stt_enabled=lambda: self.stt_enabled,
            cancel_stt_stream_task=self._cancel_stt_stream_task,
        )
        
        # [advice from AI] 프론트엔드 메시지 핸들러 (Phase 4 리팩토링)
        self.frontend_handler = FrontendHandler(
            turn_manager=self.turn_manager,
            external_connector=self.external_connector,
            stt_handler=self.stt_handler,
            get_room_name=lambda: self.room_name,
            get_stenographer_texts=lambda: self._stenographer_texts,
            set_stenographer_text=lambda k, v: self._stenographer_texts.__setitem__(k, v),
            get_broadcast_text=lambda: self._broadcast_text,
            append_broadcast_text=lambda t: setattr(self, '_broadcast_text', self._broadcast_text + t),
            send_raw_message=self._send_raw_message,
            broadcast_turn_state=self._broadcast_turn_state,
            broadcast_stenographer_list=self._broadcast_stenographer_list,
            broadcast_stt_text=self._broadcast_stt_text,
            reset_stt_text_state=self._reset_stt_text_state,
            get_current_timestamp=self.get_current_timestamp,
            set_turn_switching=self.set_turn_switching,
            get_stt_enabled=lambda: self.stt_enabled,
            get_ingress_audio_track=self._get_ingress_audio_track,
            get_or_create_stt_connector=self._get_or_create_stt_connector,
            start_stt_with_audio_track=self._start_stt_with_audio_track,
            stop_stt=self.stop_stt,
            get_stt_stream_task=lambda: self._stt_stream_task,
            set_stt_stream_task=lambda t: setattr(self, '_stt_stream_task', t),
        )
        
        self._setup_turn_callbacks()
        self._setup_caption_callbacks()
        self._setup_external_callbacks()
        self._setup_stt_connector()
        
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
    
    def _setup_stt_connector(self) -> None:
        """
        [advice from AI] STT Connector 설정 (STTHandler로 위임)
        """
        if not settings.STT_ENABLED:
            logger.info("[RoomAgent] STT 비활성화 (config)")
            return
        logger.info(f"[RoomAgent] STT 설정 준비됨 (lazy): {settings.STT_MODEL}")
    
    # [advice from AI] STT 관련 메서드 - STTHandler로 위임 (Phase 1 리팩토링)
    
    async def _broadcast_stt_text(self) -> None:
        """STT 텍스트 브로드캐스트 (STTHandler 위임)"""
        await self.stt_handler._broadcast_stt_text()
    
    async def _reset_stt_text_state(self) -> None:
        """STT 텍스트 상태 초기화 (STTHandler 위임)"""
        await self.stt_handler.reset_stt_text_state()
    
    async def start_stt(self) -> bool:
        """STT 시작 (STTHandler 위임)"""
        return await self.stt_handler.start_stt()
    
    async def stop_stt(self) -> None:
        """STT 중지 (STTHandler 위임)"""
        await self.stt_handler.stop_stt()
    
    @property
    def stt_enabled(self) -> bool:
        """STT 활성화 여부 (STTHandler 위임)"""
        return self.stt_handler.stt_enabled
    
    def set_turn_switching(self, switching: bool) -> None:
        """턴 전환 플래그 설정 (STTHandler 위임)"""
        self.stt_handler.set_turn_switching(switching)
    
    async def _start_stt_with_audio_track(self, track: "rtc.Track") -> None:
        """오디오 트랙과 함께 STT 시작 (STTHandler 위임)"""
        await self.stt_handler.start_stt_with_audio_track(track)
    
    async def _cancel_stt_stream_task(self) -> None:
        """STT 스트림 태스크 취소"""
        if self._stt_stream_task:
            self._stt_stream_task.cancel()
            try:
                await self._stt_stream_task
            except asyncio.CancelledError:
                pass
            self._stt_stream_task = None
    
    # [advice from AI] 참가자 관리 메서드 - ParticipantHandler로 위임 (Phase 2 리팩토링)
    
    async def _register_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """참가자 등록 (ParticipantHandler 위임)"""
        await self.participant_handler.register_participant(participant)
    
    async def _unregister_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """참가자 등록 해제 (ParticipantHandler 위임)"""
        await self.participant_handler.unregister_participant(participant)
    
    async def _broadcast_stenographer_list(self) -> None:
        """속기사 목록 브로드캐스트 (ParticipantHandler 위임)"""
        await self.participant_handler.broadcast_stenographer_list()
    
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
        
        try:
            from clients.redis_client import redis_client
            await redis_client.connect()
            await self.message_dispatcher.sync_to_redis()
            logger.info(f"[RoomAgent] Redis 초기 상태 저장 완료: {self.room_name}")
        except Exception as e:
            logger.warning(f"[RoomAgent] Redis 초기화 실패 (무시): {e}")
    
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
            
            # [advice from AI] Ingress 오디오 트랙 감지 플래그 설정
            if (
                participant.identity == self.INGRESS_IDENTITY
                and track.kind == rtc.TrackKind.KIND_AUDIO
            ):
                self._has_ingress_audio = True
                logger.info("[RoomAgent] Ingress 오디오 트랙 감지됨")
        
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
        
        # [advice from AI] 프론트엔드 메시지 직접 처리
        # LiveKit SDK: data_received 이벤트는 DataPacket 객체를 받음
        @self.room.on("data_received")
        def on_data_received(packet: "rtc.DataPacket"):
            if packet.participant:
                asyncio.create_task(
                    self._handle_frontend_message(packet.data, packet.participant)
                )
    
    def _check_existing_participants(self) -> None:
        """기존 참가자 확인 (Agent가 나중에 입장한 경우)"""
        for participant in self.room.remote_participants.values():
            logger.info(
                f"[RoomAgent] 기존 참가자 확인: {participant.identity}"
            )
            asyncio.create_task(self._register_participant(participant))
    
    # [advice from AI] 메시지 전송 메서드 - MessageDispatcher로 위임 (Phase 3 리팩토링)
    
    async def _broadcast_turn_state(self) -> None:
        """턴 상태 브로드캐스트 (MessageDispatcher 위임)"""
        await self.message_dispatcher.broadcast_turn_state()
    
    async def _sync_to_redis(self) -> None:
        """Redis 동기화 (MessageDispatcher 위임)"""
        await self.message_dispatcher.sync_to_redis()
    
    async def _send_raw_message(self, message: dict) -> bool:
        """브로드캐스트 메시지 전송 (MessageDispatcher 위임)"""
        return await self.message_dispatcher.send_raw_message(message)
    
    async def _send_to_participant(self, message: dict, identity: str) -> bool:
        """특정 참가자 메시지 전송 (MessageDispatcher 위임)"""
        return await self.message_dispatcher.send_to_participant(message, identity)
    
    # [advice from AI] 프론트엔드 메시지 처리 - FrontendHandler로 위임 (Phase 4 리팩토링)
    
    async def _handle_frontend_message(
        self,
        data: bytes,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """프론트엔드 메시지 처리 (FrontendHandler 위임)"""
        await self.frontend_handler.handle_message(data, participant)
    
    def _get_ingress_audio_track(self) -> Optional["rtc.Track"]:
        """Ingress 오디오 트랙 찾기"""
        if not self.room:
            return None
        
        for participant in self.room.remote_participants.values():
            if participant.identity == self.INGRESS_IDENTITY:
                for publication in participant.track_publications.values():
                    if (
                        publication.track 
                        and publication.track.kind == rtc.TrackKind.KIND_AUDIO
                    ):
                        return publication.track
        return None
    
    def _get_or_create_stt_connector(self):
        """STT Connector lazy 생성 (STTHandler 위임)"""
        return self.stt_handler._get_or_create_stt_connector()
    
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
        
        # [advice from AI] STT 정리
        await self.stop_stt()
        
        await self.message_handler.stop()
        await self.turn_manager.stop()
        await self.caption_manager.stop()
        await self.external_connector.stop()
        
        # [advice from AI] Redis 상태 정리 (이력은 유지)
        if redis_client and redis_client.is_connected:
            try:
                await redis_client.delete_room_state(self.room_name)
            except Exception as e:
                logger.debug(f"[RoomAgent] Redis 정리 실패: {e}")
        
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
