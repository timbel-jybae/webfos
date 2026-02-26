"""
DataChannel 메시지 처리 모듈.

Room 내 DataChannel을 통해 주고받는 메시지를 처리한다.
턴 관련, 자막 관련, STT/OCR 관련 메시지를 라우팅하고 응답한다.
"""

import asyncio
from typing import Optional, Callable, Awaitable, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass

from loguru import logger

try:
    from livekit import rtc
except ImportError:
    rtc = None

from .models.messages import (
    RoomMessage,
    MessageType,
    create_turn_start_message,
    create_turn_end_message,
    create_turn_grant_message,
    create_turn_deny_message,
    create_caption_update_message,
    create_caption_sync_message,
    create_system_error_message,
    create_system_info_message,
)
from .turn_manager import TurnManager

if TYPE_CHECKING:
    from .caption_manager import CaptionManager


MessageCallback = Callable[[RoomMessage], Awaitable[None]]


class MessageHandler:
    """
    DataChannel 메시지 처리기
    
    Room의 DataChannel을 통해 수신된 메시지를 파싱하고,
    적절한 핸들러로 라우팅한다.
    
    Attributes:
        room: LiveKit Room 인스턴스
        agent_identity: Agent identity (발신자 ID)
        turn_manager: TurnManager 인스턴스 (턴 메시지 처리용)
        caption_manager: CaptionManager 인스턴스 (자막 메시지 처리용)
    
    Example:
        handler = MessageHandler(agent_identity="room-agent")
        await handler.start(room, turn_manager, caption_manager)
        ...
        await handler.stop()
    """
    
    DATA_TOPIC = "webfos"
    
    def __init__(self, agent_identity: str = "room-agent"):
        """
        Args:
            agent_identity: Agent identity (메시지 발신자 ID)
        """
        self.agent_identity = agent_identity
        self.room: Optional["rtc.Room"] = None
        self.turn_manager: Optional[TurnManager] = None
        self.caption_manager: Optional["CaptionManager"] = None
        
        self._is_running = False
        self._message_handlers: Dict[MessageType, List[MessageCallback]] = {}
        
        self._setup_default_handlers()
        
        logger.info(f"[MessageHandler] 초기화: identity={agent_identity}")
    
    def _setup_default_handlers(self) -> None:
        """기본 메시지 핸들러 등록"""
        self.register_handler(MessageType.TURN_REQUEST, self._handle_turn_request)
        self.register_handler(MessageType.CAPTION_DRAFT, self._handle_caption_draft)
        self.register_handler(MessageType.CAPTION_SUBMIT, self._handle_caption_submit)
        self.register_handler(MessageType.REVIEW_EDIT, self._handle_review_edit)
        self.register_handler(MessageType.REVIEW_APPROVE, self._handle_review_approve)
        self.register_handler(MessageType.PING, self._handle_ping)
    
    async def start(
        self,
        room: "rtc.Room",
        turn_manager: Optional[TurnManager] = None,
        caption_manager: Optional["CaptionManager"] = None,
    ) -> None:
        """
        메시지 핸들러 시작
        
        Args:
            room: LiveKit Room 인스턴스
            turn_manager: TurnManager 인스턴스
            caption_manager: CaptionManager 인스턴스
        """
        if self._is_running:
            logger.warning("[MessageHandler] 이미 실행 중")
            return
        
        self.room = room
        self.turn_manager = turn_manager
        self.caption_manager = caption_manager
        self._is_running = True
        
        @room.on("data_received")
        def on_data_received(data: bytes, participant: "rtc.RemoteParticipant", topic: str):
            if topic == self.DATA_TOPIC:
                asyncio.create_task(self._process_message(data, participant))
        
        logger.info(f"[MessageHandler] 시작: room={room.name}")
    
    async def stop(self) -> None:
        """메시지 핸들러 중지"""
        if not self._is_running:
            return
        
        self._is_running = False
        self.room = None
        self.turn_manager = None
        self.caption_manager = None
        
        logger.info("[MessageHandler] 중지")
    
    async def _process_message(
        self,
        data: bytes,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        수신된 메시지 처리
        
        Args:
            data: 수신된 바이트 데이터
            participant: 발신 참가자
        """
        try:
            message = RoomMessage.from_bytes(data)
            
            logger.debug(
                f"[MessageHandler] 메시지 수신: {message.type.value} "
                f"from {participant.identity}"
            )
            
            handlers = self._message_handlers.get(message.type, [])
            for handler in handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(
                        f"[MessageHandler] 핸들러 오류: {message.type.value} - {e}"
                    )
            
            if not handlers:
                logger.warning(
                    f"[MessageHandler] 핸들러 없음: {message.type.value}"
                )
                
        except Exception as e:
            logger.error(f"[MessageHandler] 메시지 파싱 오류: {e}")
    
    def register_handler(
        self,
        message_type: MessageType,
        handler: MessageCallback,
    ) -> None:
        """
        메시지 핸들러 등록
        
        Args:
            message_type: 처리할 메시지 타입
            handler: 핸들러 함수
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
    
    def unregister_handler(
        self,
        message_type: MessageType,
        handler: MessageCallback,
    ) -> None:
        """
        메시지 핸들러 해제
        
        Args:
            message_type: 메시지 타입
            handler: 해제할 핸들러 함수
        """
        if message_type in self._message_handlers:
            try:
                self._message_handlers[message_type].remove(handler)
            except ValueError:
                pass
    
    async def send_message(
        self,
        message: RoomMessage,
        destination_identities: Optional[List[str]] = None,
    ) -> bool:
        """
        메시지 전송
        
        Args:
            message: 전송할 메시지
            destination_identities: 수신자 목록 (None이면 브로드캐스트)
            
        Returns:
            전송 성공 여부
        """
        if not self.room or not self._is_running:
            logger.warning("[MessageHandler] 전송 불가: 실행 중 아님")
            return False
        
        try:
            data = message.to_bytes()
            
            await self.room.local_participant.publish_data(
                data,
                topic=self.DATA_TOPIC,
                destination_identities=destination_identities,
            )
            
            logger.debug(
                f"[MessageHandler] 메시지 전송: {message.type.value} "
                f"to {destination_identities or 'all'}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[MessageHandler] 메시지 전송 실패: {e}")
            return False
    
    async def broadcast_turn_start(self, turn) -> bool:
        """턴 시작 브로드캐스트"""
        message = create_turn_start_message(
            sender=self.agent_identity,
            turn_id=turn.id,
            holder=turn.holder_identity,
            timestamp_ms=turn.start_timestamp_ms,
        )
        return await self.send_message(message)
    
    async def broadcast_turn_end(self, turn) -> bool:
        """턴 종료 브로드캐스트"""
        message = create_turn_end_message(
            sender=self.agent_identity,
            turn_id=turn.id,
            timestamp_ms=turn.end_timestamp_ms or 0,
        )
        return await self.send_message(message)
    
    async def send_turn_grant(self, turn, recipient: str) -> bool:
        """턴 권한 부여 메시지 전송"""
        message = create_turn_grant_message(
            sender=self.agent_identity,
            turn_id=turn.id,
            recipient=recipient,
        )
        return await self.send_message(message, destination_identities=[recipient])
    
    async def send_turn_deny(self, reason: str, recipient: str) -> bool:
        """턴 권한 거부 메시지 전송"""
        message = create_turn_deny_message(
            sender=self.agent_identity,
            reason=reason,
            recipient=recipient,
        )
        return await self.send_message(message, destination_identities=[recipient])
    
    async def send_error(
        self,
        error_code: str,
        error_message: str,
        recipient: Optional[str] = None,
    ) -> bool:
        """에러 메시지 전송"""
        message = create_system_error_message(
            sender=self.agent_identity,
            error_code=error_code,
            error_message=error_message,
        )
        destinations = [recipient] if recipient else None
        return await self.send_message(message, destination_identities=destinations)
    
    async def _handle_turn_request(self, message: RoomMessage) -> None:
        """
        턴 전환 요청 처리
        
        요청자가 현재 턴 보유자인 경우에만 전환을 수행한다.
        """
        if not self.turn_manager:
            logger.warning("[MessageHandler] TurnManager 없음")
            return
        
        requester = message.sender
        current_ts = message.payload.get("timestamp_ms", 0)
        
        success = await self.turn_manager.request_turn_switch(requester, current_ts)
        
        if success:
            new_turn = self.turn_manager.get_current_turn()
            if new_turn:
                await self.broadcast_turn_start(new_turn)
                await self.send_turn_grant(new_turn, new_turn.holder_identity)
        else:
            await self.send_turn_deny("권한 없음", requester)
    
    async def _handle_caption_draft(self, message: RoomMessage) -> None:
        """
        자막 작성 중 메시지 처리
        
        속기사가 작성 중인 자막을 CaptionManager에 등록/업데이트한다.
        """
        if not self.caption_manager or not self.turn_manager:
            return
        
        sender = message.sender
        payload = message.payload
        
        if not self.turn_manager.has_permission(sender):
            await self.send_error("NO_PERMISSION", "자막 작성 권한이 없습니다", sender)
            return
        
        segment_id = payload.get("segment_id")
        turn_id = payload.get("turn_id")
        timestamp_start_ms = payload.get("timestamp_start_ms", 0)
        text = payload.get("text", "")
        
        if segment_id:
            existing = self.caption_manager.get_segment(segment_id)
            if existing:
                self.caption_manager.update_segment(segment_id, text)
            else:
                self.caption_manager.create_segment(
                    turn_id=turn_id,
                    timestamp_start_ms=timestamp_start_ms,
                    text=text,
                    author_identity=sender,
                )
        else:
            current_turn = self.turn_manager.get_current_turn()
            if current_turn:
                self.caption_manager.create_segment(
                    turn_id=current_turn.id,
                    timestamp_start_ms=timestamp_start_ms,
                    text=text,
                    author_identity=sender,
                )
    
    async def _handle_caption_submit(self, message: RoomMessage) -> None:
        """
        자막 제출 메시지 처리
        
        속기사가 제출한 자막을 확정하고 브로드캐스트한다.
        """
        if not self.caption_manager or not self.turn_manager:
            return
        
        sender = message.sender
        payload = message.payload
        
        if not self.turn_manager.has_permission(sender):
            await self.send_error("NO_PERMISSION", "자막 제출 권한이 없습니다", sender)
            return
        
        segment_id = payload.get("segment_id")
        timestamp_end_ms = payload.get("timestamp_end_ms")
        text = payload.get("text")
        
        if not segment_id:
            return
        
        segment = self.caption_manager.get_segment(segment_id)
        if not segment:
            return
        
        if text:
            self.caption_manager.update_segment(segment_id, text)
        
        success = self.caption_manager.submit_segment(segment_id, timestamp_end_ms)
        
        if success:
            segment = self.caption_manager.get_segment(segment_id)
            if segment:
                await self.broadcast_caption_update(segment)
                
                current_turn = self.turn_manager.get_current_turn()
                if current_turn:
                    self.turn_manager.add_segment_to_current_turn(segment_id)
    
    async def _handle_review_edit(self, message: RoomMessage) -> None:
        """
        검수 수정 메시지 처리
        """
        if not self.caption_manager:
            return
        
        sender = message.sender
        payload = message.payload
        
        segment_id = payload.get("segment_id")
        new_text = payload.get("new_text")
        note = payload.get("note")
        
        if not segment_id:
            return
        
        segment = self.caption_manager.review_segment(
            segment_id=segment_id,
            reviewed_by=sender,
            new_text=new_text,
            note=note,
        )
        
        if segment:
            await self.broadcast_caption_update(segment)
    
    async def _handle_review_approve(self, message: RoomMessage) -> None:
        """
        검수 승인 메시지 처리
        """
        if not self.caption_manager:
            return
        
        sender = message.sender
        payload = message.payload
        
        segment_id = payload.get("segment_id")
        
        if not segment_id:
            return
        
        segment = self.caption_manager.review_segment(
            segment_id=segment_id,
            reviewed_by=sender,
        )
        
        if segment:
            self.caption_manager.finalize_segment(segment_id)
            segment = self.caption_manager.get_segment(segment_id)
            if segment:
                await self.broadcast_caption_update(segment)
    
    async def _handle_ping(self, message: RoomMessage) -> None:
        """Ping 메시지 처리"""
        pong = RoomMessage(
            type=MessageType.PONG,
            sender=self.agent_identity,
            payload={"original_timestamp": message.timestamp},
        )
        await self.send_message(pong, destination_identities=[message.sender])
    
    async def broadcast_caption_update(self, segment) -> bool:
        """자막 업데이트 브로드캐스트"""
        message = create_caption_update_message(
            sender=self.agent_identity,
            segment=segment.to_dict(),
        )
        return await self.send_message(message)
    
    async def broadcast_caption_sync(
        self,
        segments: List,
        current_timestamp_ms: int,
        reviewer_identities: Optional[List[str]] = None,
    ) -> bool:
        """
        자막 동기화 메시지 전송 (검수자용)
        
        Args:
            segments: 동기화할 세그먼트 리스트
            current_timestamp_ms: 현재 지연 영상 타임스탬프
            reviewer_identities: 수신 검수자 목록 (None이면 전체 검수자)
        """
        segment_dicts = [s.to_dict() for s in segments]
        message = create_caption_sync_message(
            sender=self.agent_identity,
            segments=segment_dicts,
            current_timestamp_ms=current_timestamp_ms,
        )
        return await self.send_message(message, destination_identities=reviewer_identities)
