"""
룸 관리 엔드포인트.

룸 준비, 토큰 발급, 상태 조회 API.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.schemas.room_schemas import (
    PrepareRequest,
    PrepareResponse,
    TokenRequest,
    TokenResponse,
    RoomStatus,
    RoomListResponse,
    MessageResponse,
)
from services.room_service import room_service
from managers.room_manager import room_manager

router = APIRouter()


@router.get("/prepare", response_model=PrepareResponse)
async def prepare():
    """
    룸 준비: Ingress 생성 + 기본 참가자 토큰 발급.
    
    이미 존재하는 룸이면 기존 상태 반환.
    """
    try:
        result = await room_service.prepare()
        return PrepareResponse(**result)
    except Exception as e:
        logger.error(f"[API] prepare 실패: {e}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/prepare", response_model=PrepareResponse)
async def prepare_with_options(request: PrepareRequest):
    """
    룸 준비 (옵션 지정).
    
    room_name, hls_url을 지정할 수 있음.
    """
    try:
        result = await room_service.prepare(
            room_name=request.room_name,
            hls_url=request.hls_url,
        )
        return PrepareResponse(**result)
    except Exception as e:
        logger.error(f"[API] prepare 실패: {e}")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/token", response_model=TokenResponse)
async def get_token(request: TokenRequest):
    """
    참가자 토큰 발급.
    
    룸이 준비되어 있어야 함.
    """
    # 기본 룸에서 토큰 발급 시도
    rooms = room_service.list_rooms()
    if not rooms:
        raise HTTPException(
            status_code=503,
            detail="룸이 준비되지 않았습니다. /api/prepare를 먼저 호출하세요.",
        )
    
    room_name = rooms[0]["room_name"]
    room = room_manager.get_room(room_name)
    
    token = room_service.generate_participant_token(
        room_name=room_name,
        identity=request.identity,
        name=request.name,
    )
    
    if not token:
        raise HTTPException(status_code=500, detail="토큰 생성 실패")
    
    return TokenResponse(
        token=token,
        ws_url=room.ws_url,
        room=room_name,
    )


@router.get("/rooms", response_model=RoomListResponse)
async def list_rooms():
    """전체 룸 목록 조회"""
    rooms = room_service.list_rooms()
    return RoomListResponse(rooms=[RoomStatus(**r) for r in rooms])


@router.get("/rooms/{room_name}", response_model=RoomStatus)
async def get_room_status(room_name: str):
    """특정 룸 상태 조회"""
    status = room_service.get_room_status(room_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"룸을 찾을 수 없습니다: {room_name}")
    return RoomStatus(**status)


@router.delete("/rooms/{room_name}", response_model=MessageResponse)
async def delete_room(room_name: str):
    """룸 삭제 (Ingress 포함)"""
    success = await room_service.cleanup_room(room_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"룸을 찾을 수 없습니다: {room_name}")
    return MessageResponse(message=f"룸 삭제 완료: {room_name}")
