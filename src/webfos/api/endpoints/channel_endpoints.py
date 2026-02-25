"""
채널 관리 엔드포인트.

채널 목록 조회, 채널 입장 API.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.schemas.channel_schemas import (
    ChannelInfo,
    ChannelListResponse,
    ChannelJoinRequest,
    ChannelJoinResponse,
)
from managers.channel_manager import channel_manager
from services.room_service import room_service

router = APIRouter()


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels():
    """채널 목록 조회."""
    channels = channel_manager.list_channels()
    return ChannelListResponse(
        channels=[ChannelInfo(**ch.to_dict()) for ch in channels]
    )


@router.get("/channels/{channel_id}", response_model=ChannelInfo)
async def get_channel(channel_id: str):
    """특정 채널 정보 조회"""
    channel = channel_manager.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"채널을 찾을 수 없습니다: {channel_id}")
    return ChannelInfo(**channel.to_dict())


@router.post("/channels/{channel_id}/join", response_model=ChannelJoinResponse)
async def join_channel(channel_id: str, request: ChannelJoinRequest = None):
    """
    [advice from AI] 채널 입장 — UUID 기반 동적 참가.
    role에 따라 identity가 자동 생성되고 토큰 1개가 반환된다.
    """
    channel = channel_manager.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"채널을 찾을 수 없습니다: {channel_id}")

    if not channel.is_active:
        raise HTTPException(status_code=503, detail=f"채널이 비활성 상태입니다: {channel_id}")

    role = (request.role if request else "participant") or "participant"

    try:
        result = await room_service.join_as(channel_id=channel_id, role=role)
        return ChannelJoinResponse(**result)
    except Exception as e:
        logger.error(f"[API] 채널 입장 실패: {channel_id}, {e}")
        raise HTTPException(status_code=503, detail=str(e))
