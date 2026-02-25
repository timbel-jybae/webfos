"""
[advice from AI] LiveKit 지연 Agent

룸 내부 스트림(ingress-hls-source)을 구독하여 3.5초 버퍼 후 재발행.
검수자는 이 Agent의 지연 트랙만 구독.

실행: python main.py
환경변수: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, BACKEND_URL (토큰 발급용)
"""

import asyncio
import logging
import os
import time
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

# [advice from AI] .env 로드
_env_paths = [
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / "backend" / ".env",
]
for p in _env_paths:
    if p.exists():
        load_dotenv(p)
        break
else:
    load_dotenv()

from livekit import api, rtc

# 설정
DELAY_SEC = 3.5
SOURCE_IDENTITY = "ingress-hls-source"
AGENT_IDENTITY = "delay-agent"
AGENT_NAME = "지연 스트림 (검수자용)"
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:32055")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "").strip()
if LIVEKIT_URL.startswith("://"):
    LIVEKIT_URL = "http" + LIVEKIT_URL
elif not (LIVEKIT_URL.startswith("http://") or LIVEKIT_URL.startswith("https://")):
    LIVEKIT_URL = "http://" + LIVEKIT_URL
WS_URL = LIVEKIT_URL.replace("https://", "wss://").replace("http://", "ws://")

# 버퍼 크기 (LRU: 초과 시 가장 오래된 프레임 드롭)
VIDEO_BUFFER_MAX = 120  # ~4초 @ 30fps
AUDIO_BUFFER_MAX = 200  # ~2초 @ 20 chunks/sec

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("delay-agent")


def _get_token(room_name: str) -> tuple[str, str]:
    """백엔드에서 Agent 토큰 발급. 반환: (token, ws_url)"""
    import urllib.request
    import json

    url = f"{BACKEND_URL.rstrip('/')}/api/agent-token"
    data = json.dumps({"room_name": room_name}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        out = json.load(resp)
    return out["token"], out.get("ws_url") or WS_URL


async def _fetch_token(room_name: str) -> tuple[str, str]:
    """비동기 토큰 발급. 반환: (token, ws_url)"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL.rstrip('/')}/api/agent-token",
                json={"room_name": room_name},
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"token api error: {resp.status}")
                data = await resp.json()
                return data["token"], data.get("ws_url") or WS_URL
    except ImportError:
        return _get_token(room_name)


class DelayBuffer:
    """[advice from AI] LRU 링 버퍼: (item, ready_at) 저장, ready_at 경과 시 출력"""

    def __init__(self, max_size: int, delay_sec: float):
        self._deque: deque = deque()
        self._max_size = max_size
        self._delay_sec = delay_sec

    def push(self, item, now: float | None = None):
        now = now or time.monotonic()
        ready_at = now + self._delay_sec
        if len(self._deque) >= self._max_size:
            self._deque.popleft()  # LRU: 가장 오래된 것 드롭
        self._deque.append((item, ready_at))

    def pop_ready(self, now: float | None = None):
        now = now or time.monotonic()
        out = []
        while self._deque and self._deque[0][1] <= now:
            out.append(self._deque.popleft()[0])
        return out


async def run_delay_agent():
    room_name = os.getenv("ROOM_NAME", "hls-sync-test-room")
    token, ws_url = await _fetch_token(room_name)

    room = rtc.Room()
    video_buffer = DelayBuffer(VIDEO_BUFFER_MAX, DELAY_SEC)
    audio_buffer = DelayBuffer(AUDIO_BUFFER_MAX, DELAY_SEC)

    video_source: rtc.VideoSource | None = None
    audio_source: rtc.AudioSource | None = None

    async def consume_video_stream(stream: rtc.VideoStream):
        nonlocal video_source
        async for event in stream:
            frame = event.frame
            # [advice from AI] 버퍼에 복사본 저장 (스트림 재사용 방지)
            data_copy = bytearray(frame.data)
            frame_copy = rtc.VideoFrame(frame.width, frame.height, frame.type, data_copy)
            video_buffer.push(frame_copy)
            if video_source is None:
                # 첫 프레임 수신 시 VideoSource 생성 (해상도 동적)
                video_source = rtc.VideoSource(frame.width, frame.height)
                vt = rtc.LocalVideoTrack.create_video_track("delayed-video", video_source)
                opts = rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_CAMERA,
                    video_encoding=rtc.VideoEncoding(max_framerate=30, max_bitrate=3_000_000),
                )
                await room.local_participant.publish_track(vt, opts)
                logger.info("published delayed video track %dx%d", frame.width, frame.height)

    async def consume_audio_stream(stream: rtc.AudioStream):
        nonlocal audio_source
        frame_count = 0
        try:
            async for event in stream:
                frame = event.frame
                # [advice from AI] AudioFrame 복사 (버퍼 저장용)
                data_copy = bytearray(frame.data.tobytes())
                frame_copy = rtc.AudioFrame(
                    data_copy, frame.sample_rate, frame.num_channels, frame.samples_per_channel
                )
                audio_buffer.push(frame_copy)
                frame_count += 1
                if audio_source is None:
                    audio_source = rtc.AudioSource(frame.sample_rate, frame.num_channels)
                    at = rtc.LocalAudioTrack.create_audio_track("delayed-audio", audio_source)
                    await room.local_participant.publish_track(
                        at, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
                    )
                    logger.info(
                        "published delayed audio track %dHz %dch",
                        frame.sample_rate,
                        frame.num_channels,
                    )
        except Exception as e:
            logger.error("consume_audio_stream error: %s", e, exc_info=True)
        logger.info("consume_audio_stream ended, frames=%d", frame_count)

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if participant.identity != SOURCE_IDENTITY:
            return
        logger.info("subscribed to %s from %s", track.kind, participant.identity)
        if track.kind == rtc.TrackKind.KIND_VIDEO:
            stream = rtc.VideoStream(track)
            asyncio.ensure_future(consume_video_stream(stream))
        elif track.kind == rtc.TrackKind.KIND_AUDIO:
            stream = rtc.AudioStream(track)
            asyncio.ensure_future(consume_audio_stream(stream))

    @room.on("track_published")
    def on_track_published(publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if participant.identity == SOURCE_IDENTITY:
            logger.info("source published track, will subscribe when ready")

    async def drain_buffers():
        """버퍼에서 ready된 프레임을 소스에 push"""
        while True:
            now = time.monotonic()
            for frame in video_buffer.pop_ready(now):
                if video_source:
                    try:
                        video_source.capture_frame(frame)
                    except Exception as e:
                        logger.warning("video capture_frame: %s", e)
            for frame in audio_buffer.pop_ready(now):
                if audio_source:
                    try:
                        await audio_source.capture_frame(frame)
                    except Exception as e:
                        logger.warning("audio capture_frame: %s", e)
            await asyncio.sleep(0.01)  # 10ms 간격

    asyncio.ensure_future(drain_buffers())

    logger.info("connecting to %s as %s", ws_url, AGENT_IDENTITY)
    try:
        await room.connect(
            ws_url,
            token,
            options=rtc.RoomOptions(auto_subscribe=True),
        )
    except rtc.ConnectError as e:
        logger.error("connect failed: %s", e)
        return

    logger.info("connected to room %s", room.name)

    # 이미 룸에 있는 소스 참가자 구독
    for pid, p in room.remote_participants.items():
        if p.identity == SOURCE_IDENTITY:
            for tid, pub in p.track_publications.items():
                if pub.subscribed and pub.track:
                    track = pub.track
                    if track.kind == rtc.TrackKind.KIND_VIDEO:
                        stream = rtc.VideoStream(track)
                        asyncio.ensure_future(consume_video_stream(stream))
                    elif track.kind == rtc.TrackKind.KIND_AUDIO:
                        stream = rtc.AudioStream(track)
                        asyncio.ensure_future(consume_audio_stream(stream))
            break

    # 연결 유지
    try:
        while True:
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass
    finally:
        await room.disconnect()
        logger.info("disconnected")


if __name__ == "__main__":
    asyncio.run(run_delay_agent())
