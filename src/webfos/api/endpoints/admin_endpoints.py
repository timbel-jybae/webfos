"""
[advice from AI] 관리자 대시보드용 API 엔드포인트

LiveKit API를 통해 룸 목록 및 상세 정보를 조회한다.
Redis를 통해 RoomAgent 내부 상태 (턴, 텍스트 등)도 조회 가능.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger
from typing import List, Optional, Any, Dict
from pydantic import BaseModel

from clients.livekit_client import livekit_client
from clients.redis_client import redis_client

router = APIRouter()


class ParticipantInfo(BaseModel):
    """참가자 정보"""
    identity: str
    name: Optional[str] = None
    role: Optional[str] = None
    joined_at: Optional[str] = None
    
    
class RoomSummary(BaseModel):
    """룸 요약 정보"""
    name: str
    sid: Optional[str] = None
    num_participants: int = 0
    created_at: Optional[str] = None
    metadata: Optional[str] = None


class StenographerState(BaseModel):
    """속기사 상태"""
    identity: str
    text: str = ""


class AgentState(BaseModel):
    """[advice from AI] RoomAgent 상태 (Redis에서 조회)"""
    stenographers: List[StenographerState] = []
    turn_holder: Optional[str] = None
    broadcast_text: str = ""
    updated_at: Optional[int] = None


class BroadcastHistory(BaseModel):
    """송출 이력"""
    text: str
    sender: str
    timestamp: int


class RoomDetail(BaseModel):
    """룸 상세 정보"""
    name: str
    sid: Optional[str] = None
    num_participants: int = 0
    created_at: Optional[str] = None
    metadata: Optional[str] = None
    participants: List[ParticipantInfo] = []
    # [advice from AI] RoomAgent 상태 (Redis)
    agent_state: Optional[AgentState] = None
    broadcast_history: List[BroadcastHistory] = []


class RoomsResponse(BaseModel):
    """룸 목록 응답"""
    rooms: List[RoomSummary]
    total: int


@router.get("/admin/rooms", response_model=RoomsResponse)
async def get_rooms():
    """
    전체 룸 목록 조회
    
    LiveKit API를 통해 현재 활성화된 모든 룸의 정보를 조회한다.
    [advice from AI] 'channel-' prefix가 있는 룸만 필터링하여 반환한다.
    [advice from AI] 참가자 수는 시스템 참가자(agent-, ingress-)를 제외한 실제 사용자 수
    """
    try:
        rooms_data = await livekit_client.list_rooms()
        
        rooms = []
        for room in rooms_data:
            # [advice from AI] channel- prefix가 있는 룸만 포함
            if not room.name.startswith("channel-"):
                continue
            
            # [advice from AI] 실제 사용자 수 계산 (agent, ingress 제외)
            try:
                participants = await livekit_client.list_participants(room.name)
                user_count = sum(
                    1 for p in participants 
                    if not p.identity.startswith("agent-") 
                    and not p.identity.startswith("ingress-")
                )
            except:
                user_count = 0
                
            rooms.append(RoomSummary(
                name=room.name,
                sid=room.sid,
                num_participants=user_count,
                created_at=str(room.creation_time) if room.creation_time else None,
                metadata=room.metadata,
            ))
        
        logger.debug(f"[Admin] 룸 목록 조회: {len(rooms)}개")
        
        return RoomsResponse(
            rooms=rooms,
            total=len(rooms),
        )
        
    except Exception as e:
        logger.error(f"[Admin] 룸 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/rooms/{room_name}", response_model=RoomDetail)
async def get_room_detail(room_name: str):
    """
    룸 상세 정보 조회
    
    특정 룸의 상세 정보 및 참가자 목록을 조회한다.
    [advice from AI] Redis에서 RoomAgent 상태도 함께 조회.
    """
    try:
        rooms = await livekit_client.list_rooms([room_name])
        
        if not rooms:
            raise HTTPException(status_code=404, detail=f"룸을 찾을 수 없음: {room_name}")
        
        room = rooms[0]
        
        participants_data = await livekit_client.list_participants(room_name)
        
        participants = []
        for p in participants_data:
            role = "stenographer"
            if p.identity.startswith("ingress-"):
                role = "ingress"
            elif p.identity.startswith("agent-"):
                role = "agent"
            elif p.metadata:
                try:
                    import json
                    meta = json.loads(p.metadata)
                    role = meta.get("role", "stenographer")
                except:
                    pass
            
            participants.append(ParticipantInfo(
                identity=p.identity,
                name=p.name or p.identity,
                role=role,
                joined_at=str(p.joined_at) if p.joined_at else None,
            ))
        
        # [advice from AI] Redis에서 RoomAgent 상태 조회
        agent_state = None
        broadcast_history = []
        
        if redis_client.is_connected:
            try:
                state_data = await redis_client.get_room_state(room_name)
                if state_data:
                    stenographers = [
                        StenographerState(identity=s["identity"], text=s.get("text", ""))
                        for s in state_data.get("stenographers", [])
                    ]
                    agent_state = AgentState(
                        stenographers=stenographers,
                        turn_holder=state_data.get("turn_holder"),
                        broadcast_text=state_data.get("broadcast_text", ""),
                        updated_at=state_data.get("updated_at"),
                    )
                
                history_data = await redis_client.get_broadcast_history(room_name, limit=20)
                broadcast_history = [
                    BroadcastHistory(
                        text=h.get("text", ""),
                        sender=h.get("sender", ""),
                        timestamp=h.get("timestamp", 0),
                    )
                    for h in history_data
                ]
            except Exception as e:
                logger.debug(f"[Admin] Redis 조회 실패: {e}")
        
        logger.debug(f"[Admin] 룸 상세 조회: {room_name}, 참가자 {len(participants)}명")
        
        return RoomDetail(
            name=room.name,
            sid=room.sid,
            num_participants=room.num_participants,
            created_at=str(room.creation_time) if room.creation_time else None,
            metadata=room.metadata,
            participants=participants,
            agent_state=agent_state,
            broadcast_history=broadcast_history,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Admin] 룸 상세 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
