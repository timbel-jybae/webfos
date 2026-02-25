"""
룸 관련 API 스키마 — Pydantic 모델.

요청/응답 DTO 정의.
"""

from typing import Optional, List
from pydantic import BaseModel


# === 요청 스키마 ===

class PrepareRequest(BaseModel):
    """룸 준비 요청"""
    room_name: Optional[str] = None
    hls_url: Optional[str] = None


class TokenRequest(BaseModel):
    """토큰 발급 요청"""
    identity: str
    name: Optional[str] = None


# === 응답 스키마 ===

class ParticipantToken(BaseModel):
    """참가자 토큰 정보"""
    identity: str
    name: str
    token: str


class PrepareResponse(BaseModel):
    """룸 준비 응답"""
    ws_url: str
    room: str
    participants: List[ParticipantToken]


class TokenResponse(BaseModel):
    """토큰 발급 응답"""
    token: str
    ws_url: str
    room: str


class RoomStatus(BaseModel):
    """룸 상태 정보"""
    room_name: str
    ws_url: str
    ingress_id: Optional[str] = None
    hls_url: Optional[str] = None
    created_at: str
    participant_count: int


class RoomListResponse(BaseModel):
    """룸 목록 응답"""
    rooms: List[RoomStatus]


class MessageResponse(BaseModel):
    """일반 메시지 응답"""
    message: str
    success: bool = True
