"""
채널 관련 API 스키마 — Pydantic 모델.
"""

from typing import List
from pydantic import BaseModel


class ChannelInfo(BaseModel):
    """채널 정보"""
    id: str
    name: str
    hls_url: str
    description: str = ""
    is_active: bool = False


class ChannelListResponse(BaseModel):
    """채널 목록 응답"""
    channels: List[ChannelInfo]


class ChannelJoinRequest(BaseModel):
    """
    [advice from AI] 채널 입장 요청 — role 기반 동적 참가.
    role에 따라 UUID identity가 생성되고 토큰 1개가 반환된다.
    """
    role: str = "participant"  # "participant" | "reviewer"


class ChannelJoinResponse(BaseModel):
    """
    [advice from AI] 채널 입장 응답 — 단일 참가자 토큰.
    고정 참가자 목록 대신, 요청마다 UUID 기반 identity + 토큰 1개 반환.
    """
    channel_id: str
    channel_name: str
    ws_url: str
    room: str
    identity: str
    name: str
    role: str
    token: str
