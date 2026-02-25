"""
룸 관리 비즈니스 서비스.

룸 준비, 토큰 발급 등 비즈니스 로직을 담당한다.
"""

import uuid
from typing import Dict, Any, List, Optional
from loguru import logger

from core.config import settings
from clients.livekit_client import livekit_client
from managers.room_manager import room_manager, RoomState


class RoomService:
    """
    룸 관리 비즈니스 서비스.

    - join_as(): UUID 기반 동적 참가자 토큰 발급
    - get_room_status(): 룸 상태 조회
    - cleanup_room(): 룸 정리
    """

    async def join_as(
        self,
        channel_id: str,
        role: str = "participant",
    ) -> Dict[str, Any]:
        """
        [advice from AI] 채널에 동적으로 입장 — UUID 기반 identity 생성.

        Args:
            channel_id: 채널 ID
            role: "participant" 또는 "reviewer"

        Returns:
            Dict: ws_url, room, identity, name, role, token
        """
        from managers.channel_manager import channel_manager

        channel = channel_manager.get_channel(channel_id)
        if not channel or not channel.room_name:
            raise ValueError(f"채널을 찾을 수 없거나 Room이 준비되지 않음: {channel_id}")

        room_name = channel.room_name
        short_id = uuid.uuid4().hex[:8]

        if role == "reviewer":
            identity = f"r-{short_id}"
            name = "검수자"
        else:
            identity = f"p-{short_id}"
            name = "참가자"

        token = livekit_client.generate_token(
            room_name=room_name,
            identity=identity,
            name=name,
        )

        logger.info(f"[RoomService] 토큰 발급: {identity} ({role}) -> room={room_name}")

        return {
            "channel_id": channel_id,
            "channel_name": channel.name,
            "ws_url": settings.livekit_ws_url,
            "room": room_name,
            "identity": identity,
            "name": name,
            "role": role,
            "token": token,
        }

    def get_room_status(self, room_name: str) -> Optional[Dict[str, Any]]:
        """룸 상태 조회"""
        room = room_manager.get_room(room_name)
        if not room:
            return None
        return room.to_dict()

    async def cleanup_room(self, room_name: str) -> bool:
        """룸 정리: Ingress 삭제 + 룸 상태 삭제."""
        room = room_manager.get_room(room_name)
        if not room:
            return False

        if room.ingress_id:
            try:
                await livekit_client.delete_ingress(room.ingress_id)
            except Exception as e:
                logger.warning(f"[RoomService] Ingress 삭제 실패: {e}")

        room_manager.delete_room(room_name)
        logger.info(f"[RoomService] 룸 정리 완료: {room_name}")
        return True

    def list_rooms(self) -> List[Dict[str, Any]]:
        """전체 룸 목록"""
        return [room.to_dict() for room in room_manager.list_rooms()]


# 모듈 레벨 인스턴스
room_service = RoomService()
