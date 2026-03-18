"""
Frontend Handler - 프론트엔드 메시지 처리 전담 모듈.

RoomAgent에서 분리된 프론트엔드 메시지 처리 로직을 담당합니다.
- 송출 요청 처리
- 임시 텍스트 업데이트
- 상태 요청 처리
- STT 시작/중지
- 편집 모드 시작/종료

[advice from AI] RoomAgent 리팩토링 Phase 4
"""

import asyncio
import json
from typing import Optional, Dict, Callable, Awaitable, TYPE_CHECKING

from loguru import logger

# [advice from AI] Redis 클라이언트 (상태 공유용)
try:
    from clients.redis_client import redis_client
except ImportError:
    redis_client = None

if TYPE_CHECKING:
    from livekit import rtc
    from .turn_manager import TurnManager
    from .external_connector import ExternalConnector
    from .stt_handler import STTHandler


class FrontendHandler:
    """
    프론트엔드 메시지 처리 핸들러.
    
    프론트엔드에서 보내는 DataChannel 메시지를 처리합니다.
    RoomAgent와 협력하여 동작하며, 필요한 콜백과 상태를 주입받습니다.
    """
    
    def __init__(
        self,
        turn_manager: "TurnManager",
        external_connector: "ExternalConnector",
        stt_handler: "STTHandler",
        get_room_name: Callable[[], str],
        get_stenographer_texts: Callable[[], Dict[str, str]],
        set_stenographer_text: Callable[[str, str], None],
        get_broadcast_text: Callable[[], str],
        append_broadcast_text: Callable[[str], None],
        send_raw_message: Callable[[dict], Awaitable[bool]],
        broadcast_turn_state: Callable[[], Awaitable[None]],
        broadcast_stenographer_list: Callable[[], Awaitable[None]],
        broadcast_stt_text: Callable[[], Awaitable[None]],
        reset_stt_text_state: Callable[[], Awaitable[None]],
        get_current_timestamp: Callable[[], int],
        set_turn_switching: Callable[[bool], None],
        get_stt_enabled: Callable[[], bool],
        get_ingress_audio_track: Callable[[], Optional["rtc.Track"]],
        get_or_create_stt_connector: Callable[[], Optional[object]],
        start_stt_with_audio_track: Callable[["rtc.Track"], Awaitable[None]],
        stop_stt: Callable[[], Awaitable[None]],
        get_stt_stream_task: Callable[[], Optional[asyncio.Task]],
        set_stt_stream_task: Callable[[Optional[asyncio.Task]], None],
    ):
        """
        Args:
            turn_manager: 턴 관리자 인스턴스
            external_connector: 외부 연동 모듈
            stt_handler: STT 핸들러
            get_room_name: Room 이름 반환 함수
            ... (다수의 콜백 함수)
        """
        self._turn_manager = turn_manager
        self._external_connector = external_connector
        self._stt_handler = stt_handler
        self._get_room_name = get_room_name
        self._get_stenographer_texts = get_stenographer_texts
        self._set_stenographer_text = set_stenographer_text
        self._get_broadcast_text = get_broadcast_text
        self._append_broadcast_text = append_broadcast_text
        self._send_raw_message = send_raw_message
        self._broadcast_turn_state = broadcast_turn_state
        self._broadcast_stenographer_list = broadcast_stenographer_list
        self._broadcast_stt_text = broadcast_stt_text
        self._reset_stt_text_state = reset_stt_text_state
        self._get_current_timestamp = get_current_timestamp
        self._set_turn_switching = set_turn_switching
        self._get_stt_enabled = get_stt_enabled
        self._get_ingress_audio_track = get_ingress_audio_track
        self._get_or_create_stt_connector = get_or_create_stt_connector
        self._start_stt_with_audio_track = start_stt_with_audio_track
        self._stop_stt = stop_stt
        self._get_stt_stream_task = get_stt_stream_task
        self._set_stt_stream_task = set_stt_stream_task
        
        logger.info("[FrontendHandler] 초기화 완료")
    
    async def handle_message(
        self,
        data: bytes,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        프론트엔드에서 보내는 메시지 처리
        """
        try:
            message = json.loads(data.decode())
            msg_type = message.get("type")
            sender = participant.identity
            
            logger.debug(f"[FrontendHandler] 메시지: {msg_type} from {sender}")
            
            if msg_type == "caption.broadcast":
                await self._handle_broadcast_request(sender, message)
            elif msg_type == "caption.draft":
                await self._handle_draft_update(sender, message)
            elif msg_type == "state.request":
                await self._handle_state_request(sender)
            elif msg_type == "stt.start":
                await self._handle_stt_start(sender)
            elif msg_type == "stt.stop":
                await self._handle_stt_stop(sender)
            elif msg_type == "edit.start":
                await self._handle_edit_start(sender)
            elif msg_type == "edit.end":
                await self._handle_edit_end(sender, message)
            else:
                logger.debug(f"[FrontendHandler] 알 수 없는 메시지 타입: {msg_type}")
                
        except json.JSONDecodeError:
            logger.debug("[FrontendHandler] JSON 파싱 실패")
        except Exception as e:
            logger.error(f"[FrontendHandler] 메시지 처리 오류: {e}")
    
    async def _handle_broadcast_request(self, sender: str, message: dict) -> None:
        """송출 요청 처리"""
        text = message.get("text", "")
        
        if not self._turn_manager.has_permission(sender):
            logger.warning(f"[FrontendHandler] 송출 권한 없음: {sender}")
            return
        
        logger.info(f"[FrontendHandler] 송출 요청: {sender}, text={text[:50]}...")
        
        # 1. 송출 텍스트 누적 저장
        self._append_broadcast_text(text)
        
        # 2. 송출 텍스트 브로드캐스트
        await self._send_raw_message({
            "type": "caption.broadcast",
            "text": self._get_broadcast_text(),
            "sender": sender,
        })
        
        # 3. 송출자의 입력 텍스트 초기화
        self._set_stenographer_text(sender, "")
        
        # 4. 외부 시스템에 전송
        current_ts = self._get_current_timestamp()
        await self._external_connector.send_caption_to_broadcast(text, current_ts)
        
        # 5. 턴 전환 시작
        self._set_turn_switching(True)
        logger.info("[FrontendHandler] 턴 전환 시작 - STT 브로드캐스트 차단")
        
        try:
            # 6. STT 텍스트 상태 초기화
            await self._reset_stt_text_state()
            
            # 7. 턴 전환
            await self._turn_manager.request_turn_switch(sender, current_ts)
            await self._broadcast_turn_state()
            
            # 8. 초기화된 STT 상태를 새 턴 보유자에게 전송
            await self._broadcast_stt_text()
            
            # 9. 속기사 목록 브로드캐스트
            await self._broadcast_stenographer_list()
        finally:
            # 10. 턴 전환 완료
            self._set_turn_switching(False)
            logger.info("[FrontendHandler] 턴 전환 완료 - STT 브로드캐스트 허용")
        
        # 11. Redis에 송출 이력 저장
        if redis_client and redis_client.is_connected:
            try:
                room_name = self._get_room_name()
                await redis_client.add_broadcast_history(
                    room_name,
                    {
                        "text": text,
                        "sender": sender,
                        "timestamp": current_ts,
                    }
                )
            except Exception as e:
                logger.debug(f"[FrontendHandler] Redis 이력 저장 실패: {e}")
    
    async def _handle_draft_update(self, sender: str, message: dict) -> None:
        """임시 텍스트 업데이트 처리"""
        text = message.get("text", "")
        
        # 1. 속기사별 텍스트 상태 저장
        self._set_stenographer_text(sender, text)
        
        # 2. 브로드캐스트
        await self._send_raw_message({
            "type": "caption.draft",
            "text": text,
            "sender": sender,
        })
    
    async def _handle_state_request(self, sender: str) -> None:
        """상태 요청 처리"""
        logger.info(f"[FrontendHandler] 상태 요청: {sender}")
        
        # 1. 속기사 목록 전송
        await self._broadcast_stenographer_list()
        
        # 2. 턴 상태 전송
        await self._broadcast_turn_state()
        
        # 3. 송출 텍스트 전송
        broadcast_text = self._get_broadcast_text()
        if broadcast_text:
            await self._send_raw_message({
                "type": "caption.broadcast",
                "text": broadcast_text,
                "sender": "system",
            })
        
        # 4. STT 상태 전송
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": self._get_stt_enabled(),
        })
    
    async def _handle_stt_start(self, sender: str) -> None:
        """STT 시작 요청 처리"""
        logger.info(f"[FrontendHandler] STT 시작 요청: {sender}")
        
        if self._get_stt_enabled():
            logger.warning("[FrontendHandler] STT 이미 실행 중")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": True,
                "message": "already_running",
            })
            return
        
        # 동적으로 트랙 찾기
        audio_track = self._get_ingress_audio_track()
        if not audio_track:
            logger.warning("[FrontendHandler] Ingress 오디오 트랙 없음")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": False,
                "message": "no_audio_track",
            })
            return
        
        # lazy 생성: STT 시작 시점에 커넥터 생성
        connector = self._get_or_create_stt_connector()
        if not connector:
            logger.warning("[FrontendHandler] STT Connector 생성 실패")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": False,
                "message": "stt_disabled",
            })
            return
        
        # STT 시작
        task = asyncio.create_task(
            self._start_stt_with_audio_track(audio_track)
        )
        self._set_stt_stream_task(task)
        
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": True,
            "message": "started",
        })
    
    async def _handle_stt_stop(self, sender: str) -> None:
        """STT 중지 요청 처리"""
        logger.info(f"[FrontendHandler] STT 중지 요청: {sender}")
        
        task = self._get_stt_stream_task()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._set_stt_stream_task(None)
        
        await self._stop_stt()
        
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": False,
            "message": "stopped",
        })
    
    async def _handle_edit_start(self, sender: str) -> None:
        """편집 모드 시작 요청 처리"""
        # STTHandler의 편집 모드 사용
        success = self._stt_handler.start_edit_mode(sender)
        if not success:
            logger.warning(f"[FrontendHandler] 편집 모드 시작 거부: {sender}")
            return
        
        logger.info(f"[FrontendHandler] 편집 모드 시작: {sender}")
        
        # 편집 모드 상태 브로드캐스트
        await self._send_raw_message({
            "type": "edit.status",
            "editing": True,
            "editor": sender,
        })
    
    async def _handle_edit_end(self, sender: str, message: dict) -> None:
        """편집 모드 종료 및 병합 처리"""
        edited_text = message.get("text", "")
        
        # STTHandler의 편집 모드 종료
        merged_text = self._stt_handler.end_edit_mode(sender, edited_text)
        if merged_text is None:
            logger.warning(f"[FrontendHandler] 편집 모드 종료 거부: {sender}")
            return
        
        logger.info(
            f"[FrontendHandler] 편집 완료 및 병합: "
            f"edited={len(edited_text)}자, merged={len(merged_text)}자"
        )
        
        # 편집 모드 종료 상태 브로드캐스트
        await self._send_raw_message({
            "type": "edit.status",
            "editing": False,
            "editor": "",
        })
        
        # 병합된 텍스트 브로드캐스트
        await self._broadcast_stt_text()
