"""
[advice from AI] LiveKit Agent Worker — 채널별 Room에 dispatch되는 Agent.

livekit-agents 프레임워크(v1.4+)를 사용하여 별도 프로세스로 실행된다.
Ingress 생성 시 FastAPI 서버가 이 Agent를 Room에 dispatch하면,
RoomAgent 중앙 허브가 턴 관리, 자막 병합 등을 수행한다.

VideoRouter 제거: 검수자용 영상 지연은 클라이언트 측에서 처리한다.

실행:
    cd src/webfos
    python -m agents.room_agent_worker dev
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from loguru import logger
from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli

from .room_agent import RoomAgent

AGENT_NAME = "room-agent"

try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.config import settings
    DELAY_MS = settings.AGENT_DELAY_MS
    AGENT_IDENTITY = settings.AGENT_IDENTITY
    TURN_DURATION_MS = settings.AGENT_TURN_DURATION_MS
    AUTO_SWITCH = settings.AGENT_TURN_AUTO_SWITCH
    MAX_STENOGRAPHERS = settings.AGENT_MAX_STENOGRAPHERS
    CAPTION_RETENTION_MS = settings.AGENT_CAPTION_RETENTION_MS
    STT_URL = settings.STT_SERVICE_URL
    STT_TIMEOUT = settings.STT_SERVICE_TIMEOUT
    OCR_URL = settings.OCR_SERVICE_URL
    OCR_TIMEOUT = settings.OCR_SERVICE_TIMEOUT
    BROADCAST_URL = settings.BROADCAST_OUTPUT_URL
    BROADCAST_TIMEOUT = settings.BROADCAST_OUTPUT_TIMEOUT
except ImportError:
    DELAY_MS = 3500
    AGENT_IDENTITY = "room-agent"
    TURN_DURATION_MS = 30000
    AUTO_SWITCH = False
    MAX_STENOGRAPHERS = 4
    CAPTION_RETENTION_MS = 60000
    STT_URL = ""
    STT_TIMEOUT = 5.0
    OCR_URL = ""
    OCR_TIMEOUT = 5.0
    BROADCAST_URL = ""
    BROADCAST_TIMEOUT = 10.0

server = AgentServer()

_active_agents: dict[str, RoomAgent] = {}


@server.rtc_session(agent_name=AGENT_NAME)
async def room_agent_session(ctx: JobContext):
    """
    Room에 dispatch되었을 때 실행되는 엔트리포인트.

    [advice from AI] RoomAgent 중앙 허브를 생성하고 관리한다.
    VideoRouter 제거 - 검수자용 영상 지연은 클라이언트 측 버퍼링(useDelayBuffer)으로 처리.
    
    1. Room에 연결 (모든 트랙 자동 구독)
    2. RoomAgent 시작
    3. Room이 닫힐 때까지 대기
    4. 종료 시 RoomAgent 정리
    """
    room_name = ctx.room.name
    logger.info(f"[Worker] Job 시작: room={room_name}")

    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)

    room = ctx.room
    
    agent = RoomAgent(
        delay_ms=DELAY_MS,
        turn_duration_ms=TURN_DURATION_MS,
        auto_switch=AUTO_SWITCH,
        max_stenographers=MAX_STENOGRAPHERS,
        caption_retention_ms=CAPTION_RETENTION_MS,
        stt_url=STT_URL,
        stt_timeout=STT_TIMEOUT,
        ocr_url=OCR_URL,
        ocr_timeout=OCR_TIMEOUT,
        broadcast_url=BROADCAST_URL,
        broadcast_timeout=BROADCAST_TIMEOUT,
        agent_identity=AGENT_IDENTITY,
    )
    
    _active_agents[room_name] = agent
    
    try:
        await agent.start(room=room)
        
        logger.info(
            f"[Worker] RoomAgent 시작 완료: {room_name}, "
            f"참가자 {len(room.remote_participants)}명"
        )
        
        @room.on("disconnected")
        def on_disconnected():
            logger.info(f"[Worker] Room 연결 해제: {room_name}")
        
    except Exception as e:
        logger.error(f"[Worker] RoomAgent 시작 실패: {e}")
        raise
    finally:
        pass


@server.on("shutdown")
def on_shutdown():
    """
    서버 종료 시 모든 Agent 정리
    
    [advice from AI] livekit-agents의 .on() 메서드는 동기 콜백만 지원하므로,
    비동기 정리 작업은 asyncio.create_task()로 실행한다.
    """
    logger.info("[Worker] 서버 종료, Agent 정리 시작")
    
    async def cleanup_agents():
        for room_name, agent in list(_active_agents.items()):
            try:
                await agent.stop()
                logger.info(f"[Worker] Agent 정리 완료: {room_name}")
            except Exception as e:
                logger.error(f"[Worker] Agent 정리 실패: {room_name} - {e}")
        
        _active_agents.clear()
        logger.info("[Worker] 모든 Agent 정리 완료")
    
    asyncio.create_task(cleanup_agents())


if __name__ == "__main__":
    cli.run_app(server)
