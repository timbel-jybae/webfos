"""
Message Dispatcher - 메시지 전송 전담 모듈.

RoomAgent에서 분리된 메시지 전송/브로드캐스트 로직을 담당합니다.
- 브로드캐스트 메시지 전송
- 특정 참가자 대상 메시지 전송
- Redis 상태 동기화

[advice from AI] RoomAgent 리팩토링 Phase 3
"""

import json
import time
from typing import Optional, Dict, Callable, List, TYPE_CHECKING

from loguru import logger

# [advice from AI] Redis 클라이언트 (상태 공유용)
try:
    from clients.redis_client import redis_client
except ImportError:
    redis_client = None

if TYPE_CHECKING:
    from livekit import rtc
    from .turn_manager import TurnManager


class MessageDispatcher:
    """
    메시지 전송 핸들러.
    
    LiveKit DataChannel을 통한 메시지 전송을 담당합니다.
    RoomAgent와 협력하여 동작하며, Room 인스턴스를 참조로 접근합니다.
    """
    
    def __init__(
        self,
        get_room: Callable[[], Optional["rtc.Room"]],
        get_room_name: Callable[[], str],
        turn_manager: "TurnManager",
        get_stenographer_texts: Callable[[], Dict[str, str]],
        get_broadcast_text: Callable[[], str],
    ):
        """
        Args:
            get_room: Room 인스턴스 반환 함수
            get_room_name: Room 이름 반환 함수
            turn_manager: 턴 관리자 인스턴스
            get_stenographer_texts: 속기사별 텍스트 dict 반환 함수
            get_broadcast_text: 송출 텍스트 반환 함수
        """
        self._get_room = get_room
        self._get_room_name = get_room_name
        self._turn_manager = turn_manager
        self._get_stenographer_texts = get_stenographer_texts
        self._get_broadcast_text = get_broadcast_text
        
        logger.info("[MessageDispatcher] 초기화 완료")
    
    async def send_raw_message(self, message: dict) -> bool:
        """
        프론트엔드 형식의 raw 메시지 전송 (브로드캐스트)
        """
        room = self._get_room()
        if not room:
            logger.warning("[MessageDispatcher] 메시지 전송 실패: room 없음")
            return False
        
        try:
            data = json.dumps(message).encode()
            await room.local_participant.publish_data(data)
            logger.debug(f"[MessageDispatcher] Raw 메시지 전송: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"[MessageDispatcher] 메시지 전송 실패: {e}")
            return False
    
    async def send_to_participant(self, message: dict, identity: str) -> bool:
        """
        특정 참가자에게만 메시지 전송
        
        Args:
            message: 전송할 메시지
            identity: 대상 참가자 identity
        """
        room = self._get_room()
        if not room:
            logger.warning("[MessageDispatcher] 메시지 전송 실패: room 없음")
            return False
        
        if not identity:
            logger.warning("[MessageDispatcher] 메시지 전송 실패: identity 없음")
            return False
        
        try:
            data = json.dumps(message).encode()
            await room.local_participant.publish_data(
                data,
                destination_identities=[identity]
            )
            logger.debug(f"[MessageDispatcher] 메시지 전송 to {identity}: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"[MessageDispatcher] 메시지 전송 실패 to {identity}: {e}")
            return False
    
    async def broadcast_turn_state(self) -> None:
        """
        현재 턴 상태 브로드캐스트
        """
        current_holder = self._turn_manager.get_current_holder()
        
        message = {
            "type": "turn.grant",
            "holder": current_holder,
        }
        
        await self.send_raw_message(message)
        logger.info(f"[MessageDispatcher] 턴 상태 브로드캐스트: holder={current_holder}")
        
        # Redis 상태 동기화
        await self.sync_to_redis()
    
    async def sync_to_redis(self) -> None:
        """
        Redis에 현재 상태 동기화
        
        Admin 대시보드에서 조회할 수 있도록 상태 저장.
        Redis 연결 실패 시 조용히 무시 (핵심 기능 아님).
        """
        if not redis_client or not redis_client.is_connected:
            return
        
        try:
            stenographers = self._turn_manager.get_stenographers()
            steno_texts = self._get_stenographer_texts()
            steno_list = [
                {
                    "identity": s.identity,
                    "text": steno_texts.get(s.identity, ""),
                }
                for s in stenographers
            ]
            
            state = {
                "stenographers": steno_list,
                "turn_holder": self._turn_manager.get_current_holder(),
                "broadcast_text": self._get_broadcast_text(),
                "updated_at": int(time.time() * 1000),
            }
            
            room_name = self._get_room_name()
            await redis_client.set_room_state(room_name, state)
            
        except Exception as e:
            logger.debug(f"[MessageDispatcher] Redis 동기화 실패: {e}")
