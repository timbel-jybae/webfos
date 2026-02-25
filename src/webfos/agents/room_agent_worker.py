"""
[advice from AI] LiveKit Agent Worker — 채널별 Room에 dispatch되는 Agent.

livekit-agents 프레임워크(v1.4+)를 사용하여 별도 프로세스로 실행된다.
Ingress 생성 시 FastAPI 서버가 이 Agent를 Room에 dispatch하면,
트랙을 구독하고 STT/속기 merge/이미지 분석 등을 수행한다.

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

AGENT_NAME = "room-agent"

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def room_agent(ctx: JobContext):
    """
    Room에 dispatch되었을 때 실행되는 엔트리포인트.

    1. Room에 연결 (모든 트랙 자동 구독)
    2. 트랙 구독 시 처리 태스크 생성
    3. Room이 닫힐 때까지 대기
    """
    logger.info(f"[RoomAgent] Job 시작: room={ctx.room.name}")

    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)

    room = ctx.room

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        logger.info(
            f"[RoomAgent] 트랙 구독: {participant.identity} "
            f"{track.kind} (room={room.name})"
        )
        if isinstance(track, rtc.AudioTrack):
            asyncio.create_task(_process_audio(room.name, track, participant.identity))
        elif isinstance(track, rtc.VideoTrack):
            asyncio.create_task(_process_video(room.name, track, participant.identity))

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info(f"[RoomAgent] 참가자 입장: {participant.identity} (room={room.name})")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"[RoomAgent] 참가자 퇴장: {participant.identity} (room={room.name})")

    logger.info(
        f"[RoomAgent] Room 연결 완료: {room.name}, "
        f"참가자 {len(room.remote_participants)}명"
    )


async def _process_audio(room_name: str, track: rtc.AudioTrack, identity: str):
    """
    오디오 트랙 처리 — 향후 STT + 속기 merge 연동 지점.
    """
    logger.info(f"[RoomAgent] 오디오 처리 시작: {identity} (room={room_name})")
    try:
        audio_stream = rtc.AudioStream(track)
        async for _event in audio_stream:
            pass  # TODO: STT 처리 후크
        await audio_stream.aclose()
    except Exception as e:
        logger.debug(f"[RoomAgent] 오디오 스트림 종료: {identity} - {e}")
    logger.info(f"[RoomAgent] 오디오 처리 종료: {identity} (room={room_name})")


async def _process_video(room_name: str, track: rtc.VideoTrack, identity: str):
    """
    비디오 트랙 처리 — 향후 이미지 분석 연동 지점.
    """
    logger.info(f"[RoomAgent] 비디오 처리 시작: {identity} (room={room_name})")
    try:
        video_stream = rtc.VideoStream(track)
        async for _event in video_stream:
            pass  # TODO: 이미지 분석 후크
        await video_stream.aclose()
    except Exception as e:
        logger.debug(f"[RoomAgent] 비디오 스트림 종료: {identity} - {e}")
    logger.info(f"[RoomAgent] 비디오 처리 종료: {identity} (room={room_name})")


if __name__ == "__main__":
    cli.run_app(server)
