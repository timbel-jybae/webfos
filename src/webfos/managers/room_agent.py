"""
Room Agent 관리자.

각 채널의 Room에 Agent를 입장시켜 연결을 유지하고,
향후 STT, 속기 merge, 이미지 분석 등의 기능을 수행한다.

[advice from AI] 트랙 구독 제거 — livekit-rtc의 set_subscribed(True)는
네이티브 레벨에서 프레임 디코딩을 유발하여 6채널 동시 구독 시
이벤트 루프 차단 + malloc 크래시 발생.
Ingress는 구독자 없이도 유지되므로 Agent는 Room 참여만으로 충분.
"""

import asyncio
from typing import Dict, Optional
from dataclasses import dataclass
from loguru import logger

from livekit import rtc


@dataclass
class AgentConnection:
    """Agent 연결 정보"""
    channel_id: str
    room_name: str
    room: Optional[rtc.Room] = None
    task: Optional[asyncio.Task] = None
    is_connected: bool = False


class RoomAgent:
    """
    Room Agent 싱글톤.
    
    각 채널마다 Agent를 입장시켜 Room에 참여한다.
    트랙 구독 없이 연결만 유지하며, 향후 기능 확장 시 활용.
    """
    
    AGENT_IDENTITY = "room-agent"
    AGENT_NAME = "Room Agent"
    RECONNECT_DELAY = 5

    def __init__(self):
        self._connections: Dict[str, AgentConnection] = {}
        self._running = False

    async def start(self):
        """모든 채널에 대해 Agent 시작"""
        from managers.channel_manager import channel_manager
        from clients.livekit_client import livekit_client
        from core.config import settings
        
        self._running = True
        all_channels = channel_manager.list_channels()
        
        logger.info(f"[RoomAgent] {len(all_channels)}개 채널 Agent 시작")
        
        tasks = []
        for channel in all_channels:
            room_name = f"channel-{channel.id}"
            
            conn = AgentConnection(
                channel_id=channel.id,
                room_name=room_name,
            )
            self._connections[channel.id] = conn
            
            # [advice from AI] can_subscribe=False — 트랙 구독 비활성화
            token = livekit_client.generate_token(
                room_name=room_name,
                identity=f"{self.AGENT_IDENTITY}-{channel.id}",
                name=f"{self.AGENT_NAME} ({channel.name})",
                can_subscribe=False,
            )
            
            task = asyncio.create_task(
                self._maintain_connection(conn, settings.livekit_ws_url, token)
            )
            conn.task = task
            tasks.append(task)
        
        logger.info(f"[RoomAgent] {len(tasks)}개 연결 태스크 시작됨")

    async def _maintain_connection(self, conn: AgentConnection, ws_url: str, token: str):
        """
        채널 연결 유지 (트랙 구독 없이 Room 참여만).
        연결이 끊기면 재연결을 시도한다.
        """
        while self._running:
            try:
                room = rtc.Room()
                conn.room = room
                
                @room.on("participant_connected")
                def on_participant_connected(participant: rtc.RemoteParticipant):
                    logger.debug(f"[RoomAgent] {conn.channel_id}: 참가자 입장 - {participant.identity}")

                @room.on("participant_disconnected")
                def on_participant_disconnected(participant: rtc.RemoteParticipant):
                    logger.debug(f"[RoomAgent] {conn.channel_id}: 참가자 퇴장 - {participant.identity}")

                @room.on("disconnected")
                def on_disconnected():
                    logger.warning(f"[RoomAgent] {conn.channel_id}: 연결 끊김")
                    conn.is_connected = False
                
                await room.connect(ws_url, token)
                conn.is_connected = True
                
                participants = list(room.remote_participants.values())
                logger.info(f"[RoomAgent] {conn.channel_id}: 연결 성공, 참가자 {len(participants)}명")
                
                while self._running and conn.is_connected:
                    await asyncio.sleep(1)
                
                await room.disconnect()
                
            except asyncio.CancelledError:
                logger.info(f"[RoomAgent] {conn.channel_id}: 태스크 취소됨")
                break
            except Exception as e:
                logger.error(f"[RoomAgent] {conn.channel_id}: 연결 오류 - {e}")
                conn.is_connected = False
            
            if self._running:
                logger.info(f"[RoomAgent] {conn.channel_id}: {self.RECONNECT_DELAY}초 후 재연결...")
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def stop(self):
        """모든 연결 종료"""
        self._running = False
        
        for conn in self._connections.values():
            if conn.task and not conn.task.done():
                conn.task.cancel()
            if conn.room:
                try:
                    await conn.room.disconnect()
                except Exception:
                    pass
        
        tasks = [conn.task for conn in self._connections.values() if conn.task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._connections.clear()
        logger.info("[RoomAgent] 모든 연결 종료")

    def get_connection_status(self) -> Dict[str, bool]:
        """모든 채널의 연결 상태 반환"""
        return {
            channel_id: conn.is_connected 
            for channel_id, conn in self._connections.items()
        }

    def is_channel_connected(self, channel_id: str) -> bool:
        """특정 채널의 연결 상태 확인"""
        conn = self._connections.get(channel_id)
        return conn.is_connected if conn else False


# 싱글톤 인스턴스
room_agent = RoomAgent()
