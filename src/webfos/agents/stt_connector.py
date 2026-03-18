"""
[advice from AI] STT 연동 모듈 — WhisperLive WebSocket API (aiohttp 기반)

WhisperLive 실시간 STT 서비스와 WebSocket 연결.
- 지속적인 WebSocket 연결 유지
- 서버 측 VAD (Voice Activity Detection)
- 실시간 파셜 결과 스트리밍

aiohttp 사용: websockets 패키지가 LiveKit SDK와 충돌하므로 대체
"""

import asyncio
import json
import uuid
import struct
import array
from typing import Optional, Callable, Awaitable, List, Dict, Any
from enum import Enum

from loguru import logger

# [advice from AI] aiohttp 사용 (websockets 패키지가 LiveKit SDK와 충돌)
try:
    import aiohttp
except ImportError:
    aiohttp = None

from core.config import settings


class STTState(Enum):
    """STT 연결 상태"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    WAITING = "waiting"
    CONNECTED = "connected"
    ERROR = "error"


class STTConnector:
    """
    [advice from AI] WhisperLive WebSocket 클라이언트 (aiohttp 기반)
    
    실시간 오디오 스트리밍 및 Transcription 결과 수신.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        use_vad: bool = True,
        on_partial: Optional[Callable[[str, List[Dict]], Awaitable[None]]] = None,
        on_final: Optional[Callable[[str, List[Dict]], Awaitable[None]]] = None,
    ):
        # URL에서 host/port 추출
        ws_url = settings.STT_WS_URL
        if host is None:
            if "://" in ws_url:
                url_part = ws_url.split("://")[1]
                if ":" in url_part:
                    host = url_part.split(":")[0]
                    port = int(url_part.split(":")[1].split("/")[0])
                else:
                    host = url_part.split("/")[0]
        
        self.host = host or "192.168.1.249"
        self.port = port or 30010
        self.model = model or settings.STT_MODEL
        self.language = language or settings.STT_LANGUAGE
        self.use_vad = use_vad
        
        self._on_partial = on_partial
        self._on_final = on_final
        
        self._uid = str(uuid.uuid4())
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._state = STTState.DISCONNECTED
        self._receive_task: Optional[asyncio.Task] = None
        
        self._last_text = ""
        self._send_count = 0
        self._recv_count = 0
        
    @property
    def state(self) -> STTState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == STTState.CONNECTED
    
    def _build_ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"
    
    async def connect(self) -> bool:
        """WebSocket 연결 및 설정 전송"""
        if aiohttp is None:
            logger.error("[STTConnector] aiohttp 패키지가 설치되지 않음")
            return False
        
        if self._state == STTState.CONNECTED:
            logger.warning("[STTConnector] 이미 연결됨")
            return True
        
        self._state = STTState.CONNECTING
        
        try:
            url = self._build_ws_url()
            logger.info(f"[STTConnector] 연결 시도: {url}")
            
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                url,
                heartbeat=20,
            )
            
            # 설정 전송
            config = {
                "uid": self._uid,
                "language": self.language,
                "task": "transcribe",
                "model": self.model,
                "use_vad": self.use_vad,
            }
            await self._ws.send_str(json.dumps(config))
            logger.info(f"[STTConnector] 설정 전송: uid={self._uid[:8]}..., model={self.model}")
            
            # SERVER_READY 대기
            self._state = STTState.WAITING
            try:
                msg = await asyncio.wait_for(self._ws.receive(), timeout=15.0)
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    logger.debug(f"[STTConnector] 첫 응답: {data}")
                    
                    if data.get("message") == "SERVER_READY":
                        self._state = STTState.CONNECTED
                        logger.info(f"[STTConnector] 서버 준비: backend={data.get('backend', 'unknown')}")
                        self._receive_task = asyncio.create_task(self._receive_loop())
                        return True
                    elif data.get("status") == "WAIT":
                        logger.info(f"[STTConnector] 서버 대기 중: {data.get('message', '')}")
                        msg2 = await asyncio.wait_for(self._ws.receive(), timeout=30.0)
                        if msg2.type == aiohttp.WSMsgType.TEXT:
                            data2 = json.loads(msg2.data)
                            if data2.get("message") == "SERVER_READY":
                                self._state = STTState.CONNECTED
                                self._receive_task = asyncio.create_task(self._receive_loop())
                                return True
                    else:
                        logger.warning(f"[STTConnector] 예상치 못한 응답: {data}")
                else:
                    logger.warning(f"[STTConnector] 예상치 못한 메시지 타입: {msg.type}")
                    
            except asyncio.TimeoutError:
                logger.warning("[STTConnector] 서버 준비 타임아웃")
            
            return False
            
        except Exception as e:
            logger.error(f"[STTConnector] 연결 실패: {e}")
            self._state = STTState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """WebSocket 연결 종료"""
        if self._ws and self._state == STTState.CONNECTED:
            try:
                await self._ws.send_str("END_OF_AUDIO")
            except Exception:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        
        self._state = STTState.DISCONNECTED
        logger.info("[STTConnector] 연결 종료")
    
    async def send_audio(self, audio_data: bytes) -> bool:
        """오디오 데이터 전송 (PCM16 -> float32 변환)"""
        if not self.is_connected or not self._ws:
            if self._send_count == 0:
                logger.warning(f"[STTConnector] send_audio 호출되었으나 미연결: state={self._state.value}")
            return False
        
        try:
            num_samples = len(audio_data) // 2
            int16_samples = struct.unpack(f'<{num_samples}h', audio_data)
            float32_samples = array.array('f', [s / 32768.0 for s in int16_samples])
            
            await self._ws.send_bytes(float32_samples.tobytes())
            self._send_count += 1
            
            if self._send_count % 100 == 0:
                logger.info(
                    f"[STTConnector] 전송 통계: sent={self._send_count}, "
                    f"recv={self._recv_count}, state={self._state.value}"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"[STTConnector] 오디오 전송 실패: {e}")
            return False
    
    async def _receive_loop(self) -> None:
        """WebSocket 메시지 수신 루프"""
        if not self._ws:
            return
        
        logger.info("[STTConnector] 수신 루프 시작")
        
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._recv_count += 1
                    logger.debug(f"[STTConnector] 메시지 수신 #{self._recv_count}: {msg.data[:200]}")
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    pass
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning(f"[STTConnector] WS 종료/에러: type={msg.type}")
                    break
                    
        except asyncio.CancelledError:
            logger.info("[STTConnector] 수신 루프 취소됨")
        except Exception as e:
            logger.error(f"[STTConnector] 수신 오류: {e}", exc_info=True)
        finally:
            logger.info(f"[STTConnector] 수신 루프 종료: total_recv={self._recv_count}")
            if self._state != STTState.DISCONNECTED:
                self._state = STTState.DISCONNECTED
    
    async def _handle_message(self, raw_message: str) -> None:
        """WebSocket 메시지 처리"""
        try:
            data = json.loads(raw_message)
            
            # UID 확인
            if "uid" in data and data["uid"] != self._uid:
                return
            
            # 상태 메시지
            if "status" in data:
                status = data["status"]
                if status == "WAIT":
                    self._state = STTState.WAITING
                    logger.info(f"[STTConnector] 서버 대기 중: {data.get('message', '')}")
                elif status == "ERROR":
                    self._state = STTState.ERROR
                    logger.error(f"[STTConnector] 서버 오류: {data.get('message', '')}")
                elif status == "WARNING":
                    logger.warning(f"[STTConnector] 서버 경고: {data.get('message', '')}")
                return
            
            # SERVER_READY
            if data.get("message") == "SERVER_READY":
                self._state = STTState.CONNECTED
                logger.info(f"[STTConnector] 서버 준비: backend={data.get('backend', 'unknown')}")
                return
            
            # DISCONNECT
            if data.get("message") == "DISCONNECT":
                logger.info("[STTConnector] 서버 연결 종료 요청")
                self._state = STTState.DISCONNECTED
                return
            
            # 언어 감지
            if "language" in data and "segments" not in data:
                logger.info(f"[STTConnector] 언어 감지: {data.get('language')} (prob={data.get('language_prob', 0):.2f})")
                return
            
            # Transcription 결과
            if "segments" in data:
                logger.debug(f"[STTConnector] segments 수신: {len(data['segments'])}개")
                await self._process_segments(data["segments"])
                
        except json.JSONDecodeError:
            logger.debug(f"[STTConnector] JSON 파싱 실패: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"[STTConnector] 메시지 처리 오류: {e}")
    
    async def _process_segments(self, segments: List[Dict]) -> None:
        """Transcription segments 처리"""
        if not segments:
            return
        
        # 텍스트 추출
        texts = []
        for seg in segments:
            text = seg.get("text", "").strip()
            if text and (not texts or texts[-1] != text):
                texts.append(text)
        
        full_text = " ".join(texts)
        
        if not full_text:
            return
        
        text_changed = (full_text != self._last_text)
        last_seg = segments[-1]
        is_completed = last_seg.get("completed", False)
        
        logger.debug(f"[STTConnector] segments 처리: changed={text_changed}, completed={is_completed}, text={full_text[:30]}...")
        
        if is_completed:
            if self._on_final and text_changed:
                logger.info(f"[STTConnector] 최종: {full_text[:50]}...")
                await self._on_final(full_text, segments)
                self._last_text = full_text
        else:
            if self._on_partial and text_changed:
                logger.info(f"[STTConnector] 파셜: {full_text[:50]}...")
                await self._on_partial(full_text, segments)
                self._last_text = full_text
    
    # 하위 호환성
    async def start(self) -> bool:
        return await self.connect()
    
    async def stop(self) -> None:
        await self.disconnect()
    
    async def add_audio(self, audio_data: bytes) -> None:
        await self.send_audio(audio_data)
    
    @property
    def is_running(self) -> bool:
        return self.is_connected
    
    def on_partial(self, callback: Callable[[str, List[Dict]], Awaitable[None]]) -> None:
        self._on_partial = callback
    
    def on_final(self, callback: Callable[[str, List[Dict]], Awaitable[None]]) -> None:
        self._on_final = callback
