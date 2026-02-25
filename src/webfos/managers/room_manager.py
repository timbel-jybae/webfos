"""
활성 룸 상태 관리 싱글톤 매니저.

룸 생성/조회/정리 및 Ingress 상태 추적을 담당한다.
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class RoomState:
    """룸 상태 정보"""
    room_name: str
    ws_url: str
    ingress_id: Optional[str] = None
    hls_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    participants: Dict[str, str] = field(default_factory=dict)  # identity -> token
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_name": self.room_name,
            "ws_url": self.ws_url,
            "ingress_id": self.ingress_id,
            "hls_url": self.hls_url,
            "created_at": self.created_at.isoformat(),
            "participant_count": len(self.participants),
        }


class RoomManager:
    """
    활성 룸 상태 관리 싱글톤 매니저.
    
    - get_room(): 룸 조회
    - create_room(): 룸 생성/등록
    - update_room(): 룸 상태 업데이트
    - delete_room(): 룸 삭제
    - list_rooms(): 전체 룸 목록
    """
    
    def __init__(self):
        self._rooms: Dict[str, RoomState] = {}
    
    def get_room(self, room_name: str) -> Optional[RoomState]:
        """룸 조회"""
        return self._rooms.get(room_name)
    
    def create_room(
        self,
        room_name: str,
        ws_url: str,
        ingress_id: Optional[str] = None,
        hls_url: Optional[str] = None,
    ) -> RoomState:
        """룸 생성/등록"""
        if room_name in self._rooms:
            logger.warning(f"[RoomManager] 룸 이미 존재: {room_name}, 덮어씀")
        
        room = RoomState(
            room_name=room_name,
            ws_url=ws_url,
            ingress_id=ingress_id,
            hls_url=hls_url,
        )
        self._rooms[room_name] = room
        logger.info(f"[RoomManager] 룸 생성: {room_name}")
        return room
    
    def update_room(self, room_name: str, **kwargs) -> Optional[RoomState]:
        """룸 상태 업데이트"""
        room = self._rooms.get(room_name)
        if not room:
            return None
        
        for key, value in kwargs.items():
            if hasattr(room, key):
                setattr(room, key, value)
        
        return room
    
    def add_participant_token(
        self,
        room_name: str,
        identity: str,
        token: str,
    ) -> bool:
        """참가자 토큰 저장"""
        room = self._rooms.get(room_name)
        if not room:
            return False
        room.participants[identity] = token
        return True
    
    def get_participant_token(
        self,
        room_name: str,
        identity: str,
    ) -> Optional[str]:
        """참가자 토큰 조회"""
        room = self._rooms.get(room_name)
        if not room:
            return None
        return room.participants.get(identity)
    
    def delete_room(self, room_name: str) -> bool:
        """룸 삭제"""
        if room_name in self._rooms:
            del self._rooms[room_name]
            logger.info(f"[RoomManager] 룸 삭제: {room_name}")
            return True
        return False
    
    def list_rooms(self) -> list:
        """전체 룸 목록"""
        return list(self._rooms.values())
    
    def clear(self):
        """전체 룸 정리"""
        self._rooms.clear()
        logger.info("[RoomManager] 전체 룸 정리")


# 싱글톤 인스턴스
room_manager = RoomManager()
