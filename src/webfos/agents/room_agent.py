"""
RoomAgent 메인 클래스.

실시간 자막 속기 시스템의 중앙 허브 역할을 수행한다.
- 턴 관리 (TurnManager)
- 메시지 처리 (MessageHandler)
- 자막 관리 (CaptionManager)
- 외부 연동 (ExternalConnector)

[advice from AI] VideoRouter 제거 (클라이언트 측 버퍼링 사용)
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from enum import Enum

from loguru import logger

try:
    from livekit import rtc
except ImportError:
    rtc = None

from .turn_manager import TurnManager
from .message_handler import MessageHandler
from .caption_manager import CaptionManager, MergedCaption
from .external_connector import ExternalConnector
from .models.turn import Turn
from .models.caption import CaptionSegment, STTResult, OCRResult

# [advice from AI] Redis 클라이언트 (상태 공유용)
try:
    from clients.redis_client import redis_client
except ImportError:
    redis_client = None

# [advice from AI] STT 연결 (조건부 import - 크래시 방지)
STTConnector = None

from core.config import settings


class AgentState(Enum):
    """RoomAgent 상태"""
    INITIALIZING = "initializing"
    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


class RoomAgent:
    """
    RoomAgent 중앙 허브
    
    채널별 Room에서 자막/턴 관리를 담당하는 핵심 클래스.
    
    Attributes:
        room: LiveKit Room 인스턴스
        room_name: Room 이름
        state: Agent 상태
        turn_manager: 턴 관리 모듈
        caption_manager: 자막 관리 모듈
        external_connector: 외부 연동 모듈
        message_handler: DataChannel 메시지 처리기
    
    Example:
        agent = RoomAgent(
            delay_ms=3500,
            turn_duration_ms=30000,
        )
        await agent.start(room)
        ...
        await agent.stop()
    """
    
    INGRESS_IDENTITY = "ingress-hls-source"
    
    def __init__(
        self,
        delay_ms: int = 3500,
        turn_duration_ms: int = 30000,
        auto_switch: bool = False,
        max_stenographers: int = 4,
        caption_retention_ms: int = 60000,
        stt_url: str = "",
        stt_timeout: float = 5.0,
        ocr_url: str = "",
        ocr_timeout: float = 5.0,
        broadcast_url: str = "",
        broadcast_timeout: float = 10.0,
        agent_identity: str = "room-agent",
    ):
        """
        Args:
            delay_ms: 검수자용 영상 지연 시간 (밀리초, 클라이언트 측 참조용)
            turn_duration_ms: 기본 턴 지속 시간 (밀리초)
            auto_switch: 자동 턴 전환 활성화 여부
            max_stenographers: 최대 속기사 수
            caption_retention_ms: 자막 버퍼 보관 시간 (밀리초)
            stt_url: STT 서비스 URL (빈 문자열이면 비활성화)
            stt_timeout: STT 서비스 타임아웃 (초)
            ocr_url: OCR 서비스 URL (빈 문자열이면 비활성화)
            ocr_timeout: OCR 서비스 타임아웃 (초)
            broadcast_url: 방송국 전송 URL (빈 문자열이면 비활성화)
            broadcast_timeout: 방송국 전송 타임아웃 (초)
            agent_identity: Agent identity
        """
        self.room: Optional["rtc.Room"] = None
        self.room_name: str = ""
        self.state: AgentState = AgentState.INITIALIZING
        self.agent_identity = agent_identity
        self.delay_ms = delay_ms
        
        self._start_time_ms: int = 0
        
        self.turn_manager = TurnManager(
            turn_duration_ms=turn_duration_ms,
            auto_switch=auto_switch,
            max_stenographers=max_stenographers,
        )
        
        self.caption_manager = CaptionManager(
            retention_ms=caption_retention_ms,
        )
        
        self.external_connector = ExternalConnector(
            stt_url=stt_url,
            stt_timeout=stt_timeout,
            ocr_url=ocr_url,
            ocr_timeout=ocr_timeout,
            broadcast_url=broadcast_url,
            broadcast_timeout=broadcast_timeout,
        )
        
        self.message_handler = MessageHandler(
            agent_identity=agent_identity,
        )
        
        # [advice from AI] 속기사별 텍스트 상태 및 송출 텍스트 중앙 관리
        self._stenographer_texts: Dict[str, str] = {}  # identity -> 현재 입력 텍스트
        self._broadcast_text: str = ""  # 현재 송출된 텍스트
        
        # [advice from AI] STT 상태 관리
        self._stt_enabled: bool = False  # STT 활성화 플래그
        self._stt_partial_text: str = ""  # 파셜 텍스트
        self._stt_connector: Optional["STTConnector"] = None
        self._has_ingress_audio: bool = False  # Ingress 오디오 트랙 존재 여부
        self._stt_stream_task: Optional[asyncio.Task] = None  # STT 스트림 태스크
        self._stt_last_final_text: str = ""  # 마지막으로 전송한 final 텍스트 (중복 방지)
        
        self._setup_turn_callbacks()
        self._setup_caption_callbacks()
        self._setup_external_callbacks()
        self._setup_stt_connector()
        
        logger.info(
            f"[RoomAgent] 초기화: delay={delay_ms}ms, "
            f"turn_duration={turn_duration_ms}ms"
        )
    
    def _setup_turn_callbacks(self) -> None:
        """턴 관련 콜백 설정"""
        
        async def on_turn_start(turn: Turn) -> None:
            await self.message_handler.broadcast_turn_start(turn)
            if turn.holder_identity:
                await self.message_handler.send_turn_grant(
                    turn, turn.holder_identity
                )
        
        async def on_turn_end(turn: Turn) -> None:
            await self.message_handler.broadcast_turn_end(turn)
            self.caption_manager.merge_segments(turn.id)
        
        self.turn_manager.on_turn_start(on_turn_start)
        self.turn_manager.on_turn_end(on_turn_end)
    
    def _setup_caption_callbacks(self) -> None:
        """자막 관련 콜백 설정"""
        
        async def on_segment_submitted(segment: CaptionSegment) -> None:
            await self.message_handler.broadcast_caption_update(segment)
        
        self.caption_manager.on_segment_submitted(on_segment_submitted)
    
    def _setup_external_callbacks(self) -> None:
        """외부 연동 콜백 설정"""
        
        async def on_stt_result(result: STTResult) -> None:
            self.caption_manager.add_stt_result(result)
        
        async def on_ocr_result(result: OCRResult) -> None:
            self.caption_manager.add_ocr_result(result)
        
        self.external_connector.on_stt_result(on_stt_result)
        self.external_connector.on_ocr_result(on_ocr_result)
    
    def _setup_stt_connector(self) -> None:
        """
        [advice from AI] STT Connector 설정 (WhisperLive WebSocket API)
        
        lazy 초기화: 실제 STT 시작 시점에 생성
        """
        if not settings.STT_ENABLED:
            logger.info("[RoomAgent] STT 비활성화 (config)")
            return
        
        # [advice from AI] 실제 커넥터 생성은 _get_or_create_stt_connector에서 수행
        logger.info(f"[RoomAgent] STT 설정 준비됨 (lazy): {settings.STT_MODEL}")
    
    def _get_or_create_stt_connector(self):
        """
        [advice from AI] STT Connector lazy 생성 및 lazy import
        
        STTConnector import 자체가 LiveKit SDK와 충돌할 수 있으므로
        실제 필요 시점에만 import
        """
        if self._stt_connector:
            return self._stt_connector
        
        if not settings.STT_ENABLED:
            logger.info("[RoomAgent] STT 비활성화 (config)")
            return None
        
        # [advice from AI] Lazy import - 실제 사용 시점에만 import
        try:
            from .stt_connector import STTConnector as STTConnectorClass
            logger.info("[RoomAgent] STTConnector import 성공")
        except ImportError as e:
            logger.error(f"[RoomAgent] STTConnector import 실패: {e}")
            return None
        except Exception as e:
            logger.error(f"[RoomAgent] STTConnector import 예외: {e}")
            return None
        
        try:
            self._stt_connector = STTConnectorClass(
                model=settings.STT_MODEL,
                language=settings.STT_LANGUAGE,
                use_vad=True,
                on_partial=self._on_stt_partial,
                on_final=self._on_stt_final,
            )
            logger.info(f"[RoomAgent] STT Connector 생성: {settings.STT_MODEL}")
            return self._stt_connector
        except Exception as e:
            logger.error(f"[RoomAgent] STT Connector 생성 예외: {e}")
            return None
    
    def _extract_new_text(self, current_text: str, previous_text: str) -> str:
        """
        [advice from AI] 이전 텍스트와 비교하여 새로운 부분만 추출
        
        WhisperLive는 전체 컨텍스트를 반환하므로, 이전에 이미 전송한 부분을 제외하고
        새롭게 추가된 부분만 추출합니다.
        
        Args:
            current_text: 현재 받은 전체 텍스트
            previous_text: 이전에 전송한 텍스트
        
        Returns:
            새로운 부분 텍스트
        """
        if not previous_text:
            return current_text
        
        # 이전 텍스트가 현재 텍스트의 시작 부분에 포함되어 있는지 확인
        if current_text.startswith(previous_text):
            new_part = current_text[len(previous_text):].strip()
            return new_part
        
        # 이전 텍스트의 끝부분이 현재 텍스트에 포함되어 있는지 확인 (오버랩 감지)
        for i in range(len(previous_text), 0, -1):
            suffix = previous_text[-i:]
            if current_text.startswith(suffix):
                new_part = current_text[i:].strip()
                return new_part
        
        # 전혀 다른 텍스트면 그대로 반환
        return current_text
    
    async def _on_stt_partial(self, text: str, segments: list) -> None:
        """
        [advice from AI] STT 파셜 결과 콜백
        
        파셜 텍스트를 모든 참가자에게 broadcast.
        이전 final 이후의 새로운 부분만 전송합니다.
        
        Args:
            text: 파셜 텍스트 (전체 컨텍스트)
            segments: WhisperLive 세그먼트 리스트
        """
        # [advice from AI] 새로운 부분만 추출
        new_text = self._extract_new_text(text, self._stt_last_final_text)
        
        if not new_text:
            return  # 새로운 텍스트가 없으면 전송 안 함
        
        self._stt_partial_text = new_text
        
        await self._send_raw_message({
            "type": "stt.partial",
            "text": new_text,
            "timestamp": self.get_current_timestamp(),
        })
        
        logger.debug(f"[RoomAgent] STT partial: {new_text[:50]}...")
    
    async def _on_stt_final(self, text: str, segments: list) -> None:
        """
        [advice from AI] STT 최종 결과 콜백
        
        최종 텍스트를 모든 참가자에게 broadcast.
        이전 final 이후의 새로운 부분만 전송하고, 마지막 final 텍스트를 갱신합니다.
        
        Args:
            text: 최종 텍스트 (전체 컨텍스트)
            segments: WhisperLive 세그먼트 리스트
        """
        # [advice from AI] 새로운 부분만 추출
        new_text = self._extract_new_text(text, self._stt_last_final_text)
        
        if not new_text:
            return  # 새로운 텍스트가 없으면 전송 안 함
        
        self._stt_partial_text = ""
        
        await self._send_raw_message({
            "type": "stt.final",
            "text": new_text,
            "timestamp": self.get_current_timestamp(),
        })
        
        # [advice from AI] 마지막 final 텍스트 갱신 (중복 방지)
        self._stt_last_final_text = text
        
        logger.info(f"[RoomAgent] STT final: {new_text[:50]}...")
    
    async def start_stt(self) -> bool:
        """
        [advice from AI] STT 시작
        
        Returns:
            성공 여부
        """
        if not self._stt_connector:
            logger.warning("[RoomAgent] STT Connector 없음")
            return False
        
        if self._stt_enabled:
            logger.warning("[RoomAgent] STT 이미 실행 중")
            return True
        
        success = await self._stt_connector.connect()
        if success:
            self._stt_enabled = True
            self._stt_last_final_text = ""  # 새 세션 시작 시 리셋
            logger.info("[RoomAgent] STT 시작됨")
        
        return success
    
    async def stop_stt(self) -> None:
        """
        [advice from AI] STT 중지
        """
        if not self._stt_connector:
            return
        
        await self._stt_connector.disconnect()
        self._stt_enabled = False
        self._stt_partial_text = ""
        self._stt_last_final_text = ""  # 세션 종료 시 리셋
        logger.info("[RoomAgent] STT 중지됨")
    
    @property
    def stt_enabled(self) -> bool:
        """STT 활성화 여부"""
        return self._stt_enabled
    
    async def _start_stt_with_audio_track(self, track: "rtc.Track") -> None:
        """
        [advice from AI] 오디오 트랙과 함께 STT 시작
        
        Args:
            track: LiveKit 오디오 트랙
        """
        if not await self.start_stt():
            logger.error("[RoomAgent] STT 시작 실패")
            return
        
        logger.info("[RoomAgent] 오디오 트랙 STT 처리 시작")
        
        # [advice from AI] 오디오 버퍼링 및 리샘플링 설정
        audio_buffer = bytearray()
        target_sample_rate = 16000  # WhisperLive 요구사항
        buffer_duration_ms = 100    # 100ms 단위로 전송
        min_rms_threshold = 50      # 무음 필터링 임계값 (0-32768)
        
        frame_count = 0
        source_sample_rate = None
        
        try:
            # [advice from AI] rtc.AudioStream 생성을 별도 try-except로 감싸서 안전하게 처리
            try:
                audio_stream = rtc.AudioStream(track)
                logger.info("[RoomAgent] AudioStream 생성 성공")
            except Exception as stream_err:
                logger.error(f"[RoomAgent] AudioStream 생성 실패: {stream_err}")
                await self.stop_stt()
                return
            
            async for frame_event in audio_stream:
                if not self._stt_enabled:
                    break
                
                frame = frame_event.frame
                
                # [advice from AI] 첫 프레임에서 샘플레이트 확인
                if frame_count == 0:
                    source_sample_rate = frame.sample_rate
                    samples_per_channel = frame.samples_per_channel
                    num_channels = frame.num_channels
                    logger.info(
                        f"[RoomAgent] 오디오 프레임 정보: "
                        f"sample_rate={source_sample_rate}Hz, "
                        f"channels={num_channels}, "
                        f"samples={samples_per_channel}"
                    )
                
                frame_count += 1
                
                # 오디오 데이터 가져오기
                audio_data = frame.data.tobytes()
                
                # [advice from AI] 리샘플링 (48kHz → 16kHz)
                if source_sample_rate and source_sample_rate != target_sample_rate:
                    audio_data = self._resample_audio(
                        audio_data, 
                        source_sample_rate, 
                        target_sample_rate,
                        frame.num_channels
                    )
                
                # 버퍼에 추가
                audio_buffer.extend(audio_data)
                
                # [advice from AI] 일정 크기 모이면 전송 (100ms 분량)
                buffer_size = target_sample_rate * 2 * buffer_duration_ms // 1000  # 16bit mono
                if len(audio_buffer) >= buffer_size:
                    chunk = bytes(audio_buffer[:buffer_size])
                    audio_buffer = audio_buffer[buffer_size:]
                    
                    # [advice from AI] 무음 필터링 - RMS 계산
                    rms = self._calculate_rms(chunk)
                    if rms > min_rms_threshold:
                        await self._stt_connector.send_audio(chunk)
                    # else: 무음 스킵
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[RoomAgent] 오디오 스트림 처리 오류: {e}")
        finally:
            logger.info(f"[RoomAgent] 오디오 트랙 STT 처리 종료 (총 {frame_count} 프레임)")
    
    def _resample_audio(
        self, 
        audio_data: bytes, 
        source_rate: int, 
        target_rate: int,
        num_channels: int
    ) -> bytes:
        """
        [advice from AI] 오디오 리샘플링 (간단한 선형 보간)
        
        Args:
            audio_data: PCM16 오디오 바이트
            source_rate: 원본 샘플레이트
            target_rate: 목표 샘플레이트
            num_channels: 채널 수
        
        Returns:
            리샘플링된 PCM16 바이트
        """
        import struct
        import array
        
        # int16 샘플로 변환
        num_samples = len(audio_data) // 2
        samples = struct.unpack(f'<{num_samples}h', audio_data)
        
        # 스테레오면 모노로 변환 (왼쪽+오른쪽 평균)
        if num_channels == 2:
            mono_samples = []
            for i in range(0, len(samples), 2):
                if i + 1 < len(samples):
                    mono_samples.append((samples[i] + samples[i + 1]) // 2)
            samples = mono_samples
        
        # 리샘플링 비율
        ratio = source_rate / target_rate
        new_length = int(len(samples) / ratio)
        
        # 선형 보간으로 리샘플링
        resampled = array.array('h')
        for i in range(new_length):
            src_idx = i * ratio
            idx = int(src_idx)
            frac = src_idx - idx
            
            if idx + 1 < len(samples):
                value = int(samples[idx] * (1 - frac) + samples[idx + 1] * frac)
            else:
                value = samples[idx] if idx < len(samples) else 0
            
            resampled.append(max(-32768, min(32767, value)))
        
        return resampled.tobytes()
    
    def _calculate_rms(self, audio_data: bytes) -> float:
        """
        [advice from AI] 오디오 RMS (Root Mean Square) 계산
        
        Args:
            audio_data: PCM16 오디오 바이트
        
        Returns:
            RMS 값 (0-32768 범위)
        """
        import struct
        import math
        
        num_samples = len(audio_data) // 2
        if num_samples == 0:
            return 0
        
        samples = struct.unpack(f'<{num_samples}h', audio_data)
        sum_squares = sum(s * s for s in samples)
        rms = math.sqrt(sum_squares / num_samples)
        
        return rms
    
    async def start(
        self,
        room: "rtc.Room",
    ) -> None:
        """
        RoomAgent 시작
        
        Args:
            room: LiveKit Room 인스턴스
        """
        self.room = room
        self.room_name = room.name
        self.state = AgentState.READY
        self._start_time_ms = int(time.time() * 1000)
        
        logger.info(f"[RoomAgent] 시작: room={self.room_name}")
        
        await self.caption_manager.start()
        await self.external_connector.start()
        
        await self.message_handler.start(
            room=room,
            turn_manager=self.turn_manager,
            caption_manager=self.caption_manager,
        )
        
        self._setup_event_handlers()
        self._check_existing_participants()
        
        self.state = AgentState.ACTIVE
    
    def _setup_event_handlers(self) -> None:
        """Room 이벤트 핸들러 설정"""
        
        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track: "rtc.Track",
            publication: "rtc.RemoteTrackPublication",
            participant: "rtc.RemoteParticipant",
        ):
            logger.info(
                f"[RoomAgent] 트랙 구독: {participant.identity} "
                f"{track.kind} (room={self.room_name})"
            )
            
            # [advice from AI] Ingress 오디오 트랙 감지 플래그 설정
            if (
                participant.identity == self.INGRESS_IDENTITY
                and track.kind == rtc.TrackKind.KIND_AUDIO
            ):
                self._has_ingress_audio = True
                logger.info("[RoomAgent] Ingress 오디오 트랙 감지됨")
        
        @self.room.on("track_unsubscribed")
        def on_track_unsubscribed(
            track: "rtc.Track",
            publication: "rtc.RemoteTrackPublication",
            participant: "rtc.RemoteParticipant",
        ):
            logger.info(
                f"[RoomAgent] 트랙 구독 해제: {participant.identity} "
                f"{track.kind} (room={self.room_name})"
            )
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: "rtc.RemoteParticipant"):
            logger.info(
                f"[RoomAgent] 참가자 입장: {participant.identity} "
                f"(room={self.room_name})"
            )
            asyncio.create_task(
                self._register_participant(participant)
            )
        
        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: "rtc.RemoteParticipant"):
            logger.info(
                f"[RoomAgent] 참가자 퇴장: {participant.identity} "
                f"(room={self.room_name})"
            )
            asyncio.create_task(
                self._unregister_participant(participant)
            )
        
        # [advice from AI] 프론트엔드 메시지 직접 처리
        # LiveKit SDK: data_received 이벤트는 DataPacket 객체를 받음
        @self.room.on("data_received")
        def on_data_received(packet: "rtc.DataPacket"):
            if packet.participant:
                asyncio.create_task(
                    self._handle_frontend_message(packet.data, packet.participant)
                )
    
    def _check_existing_participants(self) -> None:
        """기존 참가자 확인 (Agent가 나중에 입장한 경우)"""
        for participant in self.room.remote_participants.values():
            logger.info(
                f"[RoomAgent] 기존 참가자 확인: {participant.identity}"
            )
            asyncio.create_task(self._register_participant(participant))
    
    async def _register_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        참가자 등록
        
        participant metadata에서 role 정보를 추출하여 TurnManager에 등록한다.
        metadata 형식: {"role": "stenographer" | "reviewer", "name": "..."}
        
        [advice from AI] 속기사 등록 시:
        - 속기사 목록 브로드캐스트
        - 현재 턴이 없으면 첫 번째 속기사에게 턴 부여
        """
        identity = participant.identity
        
        # [advice from AI] 시스템 참가자 필터링 (ingress, agent 등)
        if identity == self.INGRESS_IDENTITY:
            return
        if identity.startswith("agent-"):
            logger.debug(f"[RoomAgent] Agent identity 무시: {identity}")
            return
        
        role = "stenographer"
        name = identity
        
        if participant.metadata:
            try:
                import json
                meta = json.loads(participant.metadata)
                role = meta.get("role", "stenographer")
                name = meta.get("name", identity)
            except (json.JSONDecodeError, TypeError):
                pass
        
        success = self.turn_manager.register_participant(identity, role, name)
        if success:
            logger.info(
                f"[RoomAgent] 참가자 등록 완료: {identity} ({role})"
            )
            
            # [advice from AI] 속기사 등록 시 목록 브로드캐스트 및 턴 관리
            if role == "stenographer":
                # 텍스트 상태 초기화
                self._stenographer_texts[identity] = ""
                
                await self._broadcast_stenographer_list()
                
                # [advice from AI] 송출 권한 로직 개선
                # 1. 현재 턴 보유자 확인
                # 2. 턴 보유자가 없거나 유효하지 않으면 (퇴장한 참가자 등)
                #    -> 현재 등록된 속기사 중 첫 번째에게 턴 부여
                # 3. 항상 1명은 송출권한을 갖고 있어야 함
                current_holder = self.turn_manager.get_current_holder()
                registered_stenos = [s.identity for s in self.turn_manager.get_stenographers()]
                
                # 턴 보유자가 유효한지 확인 (현재 등록된 속기사인지)
                holder_is_valid = current_holder and current_holder in registered_stenos
                
                if not holder_is_valid:
                    # 턴 보유자가 없거나 유효하지 않음 -> 첫 번째 속기사에게 턴 부여
                    if registered_stenos:
                        first_steno = registered_stenos[0]
                        # 기존 턴이 있으면 종료
                        if self.turn_manager._current_turn:
                            current_ts = self.get_current_timestamp()
                            await self.turn_manager.end_turn(current_ts)
                        
                        turn = await self.start_turn(first_steno)
                        if turn:
                            logger.info(f"[RoomAgent] 송출 권한 부여 (첫 번째 속기사): {first_steno}")
                        else:
                            logger.error(f"[RoomAgent] 송출 권한 부여 실패: {first_steno}")
                else:
                    # 유효한 턴 보유자 있음
                    logger.info(f"[RoomAgent] 기존 송출 권한 보유자: {current_holder}")
                
                # 모든 참가자에게 현재 턴 상태 브로드캐스트
                await self._broadcast_turn_state()
                
                # 신규 참가자에게 현재 송출 텍스트 전송
                if self._broadcast_text:
                    await self._send_raw_message({
                        "type": "caption.broadcast",
                        "text": self._broadcast_text,
                        "sender": "system",
                    })
    
    async def _unregister_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """참가자 등록 해제"""
        identity = participant.identity
        
        # [advice from AI] 시스템 참가자 필터링 (ingress, agent 등)
        if identity == self.INGRESS_IDENTITY:
            return
        if identity.startswith("agent-"):
            return
        
        was_turn_holder = self.turn_manager.get_current_holder() == identity
        was_stenographer = identity in [
            p.identity for p in self.turn_manager.get_stenographers()
        ]
        
        # [advice from AI] 먼저 참가자 해제 (중요: 턴 전환 전에 해제해야 퇴장자가 다시 턴을 받지 않음)
        self.turn_manager.unregister_participant(identity)
        
        # [advice from AI] 속기사였으면 텍스트 상태 삭제
        if was_stenographer:
            self._stenographer_texts.pop(identity, None)
        
        # [advice from AI] 턴 보유자였으면 다음 속기사에게 전환 (참가자 해제 후)
        if was_turn_holder:
            current_ts = self.get_current_timestamp()
            
            # 먼저 현재 턴 종료 (중요: start_turn은 활성 턴이 있으면 실패함)
            if self.turn_manager._current_turn and self.turn_manager._current_turn.is_active():
                await self.turn_manager.end_turn(current_ts)
                logger.info(f"[RoomAgent] 턴 종료 (퇴장자: {identity})")
            
            # 남은 속기사 확인
            remaining = self.turn_manager.get_stenographers()
            if remaining:
                # 남은 속기사 중 첫 번째에게 턴 부여
                turn = await self.turn_manager.start_turn(remaining[0].identity, current_ts)
                if turn:
                    logger.info(f"[RoomAgent] 턴 승계 완료: {remaining[0].identity}")
                else:
                    logger.error(f"[RoomAgent] 턴 승계 실패: {remaining[0].identity}")
            else:
                logger.info("[RoomAgent] 모든 속기사 퇴장, 턴 종료")
        
        # [advice from AI] 속기사였으면 목록/턴 브로드캐스트
        if was_stenographer:
            await self._broadcast_stenographer_list()
            await self._broadcast_turn_state()
            
            # [advice from AI] 모든 속기사 퇴장 시 송출 텍스트 리셋 및 STT 중지
            remaining_stenos = self.turn_manager.get_stenographers()
            if not remaining_stenos:
                self._broadcast_text = ""
                logger.info("[RoomAgent] 모든 속기사 퇴장, 송출 텍스트 리셋")
                
                # STT 활성화 상태면 중지
                if self._stt_enabled:
                    if self._stt_stream_task:
                        self._stt_stream_task.cancel()
                        try:
                            await self._stt_stream_task
                        except asyncio.CancelledError:
                            pass
                        self._stt_stream_task = None
                    await self.stop_stt()
                    await self._send_raw_message({
                        "type": "stt.status",
                        "enabled": False,
                        "message": "all_stenographers_left",
                    })
                    logger.info("[RoomAgent] 모든 속기사 퇴장, STT 중지")
            
            logger.info(f"[RoomAgent] 속기사 퇴장 처리 완료: {identity}")
    
    async def _broadcast_stenographer_list(self) -> None:
        """
        [advice from AI] 속기사 목록 브로드캐스트 (현재 텍스트 상태 포함)
        
        프론트엔드에서 사용하는 메시지 형식:
        { type: 'stenographer.list', stenographers: [{ identity, text }] }
        """
        stenographers = self.turn_manager.get_stenographers()
        steno_list = [
            {
                "identity": s.identity, 
                "text": self._stenographer_texts.get(s.identity, "")
            } 
            for s in stenographers
        ]
        
        message = {
            "type": "stenographer.list",
            "stenographers": steno_list,
        }
        
        await self._send_raw_message(message)
        logger.info(f"[RoomAgent] 속기사 목록 브로드캐스트: {len(steno_list)}명")
    
    async def _broadcast_turn_state(self) -> None:
        """
        [advice from AI] 현재 턴 상태 브로드캐스트
        
        프론트엔드에서 사용하는 메시지 형식:
        { type: 'turn.grant', holder: 'identity' }
        """
        current_holder = self.turn_manager.get_current_holder()
        
        message = {
            "type": "turn.grant",
            "holder": current_holder,
        }
        
        await self._send_raw_message(message)
        logger.info(f"[RoomAgent] 턴 상태 브로드캐스트: holder={current_holder}")
        
        # [advice from AI] Redis 상태 동기화
        await self._sync_to_redis()
    
    async def _sync_to_redis(self) -> None:
        """
        [advice from AI] Redis에 현재 상태 동기화
        
        Admin 대시보드에서 조회할 수 있도록 상태 저장.
        Redis 연결 실패 시 조용히 무시 (핵심 기능 아님).
        """
        if not redis_client or not redis_client.is_connected:
            return
        
        try:
            stenographers = self.turn_manager.get_stenographers()
            steno_list = [
                {
                    "identity": s.identity,
                    "text": self._stenographer_texts.get(s.identity, ""),
                }
                for s in stenographers
            ]
            
            state = {
                "stenographers": steno_list,
                "turn_holder": self.turn_manager.get_current_holder(),
                "broadcast_text": self._broadcast_text,
                "updated_at": int(time.time() * 1000),
            }
            
            await redis_client.set_room_state(self.room_name, state)
            
        except Exception as e:
            logger.debug(f"[RoomAgent] Redis 동기화 실패: {e}")
    
    async def _send_raw_message(self, message: dict) -> bool:
        """
        [advice from AI] 프론트엔드 형식의 raw 메시지 전송
        """
        if not self.room:
            logger.warning("[RoomAgent] 메시지 전송 실패: room 없음")
            return False
        
        try:
            import json
            data = json.dumps(message).encode()
            await self.room.local_participant.publish_data(data)
            logger.debug(f"[RoomAgent] Raw 메시지 전송: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"[RoomAgent] 메시지 전송 실패: {e}")
            return False
    
    async def _handle_frontend_message(
        self,
        data: bytes,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        [advice from AI] 프론트엔드에서 보내는 메시지 처리
        
        메시지 형식:
        - { type: 'caption.broadcast', text: '...' }: 송출 요청
        - { type: 'caption.draft', text: '...' }: 임시 텍스트 업데이트
        """
        try:
            import json
            message = json.loads(data.decode())
            msg_type = message.get("type")
            sender = participant.identity
            
            logger.debug(f"[RoomAgent] 프론트엔드 메시지: {msg_type} from {sender}")
            
            if msg_type == "caption.broadcast":
                await self._handle_broadcast_request(sender, message)
            elif msg_type == "caption.draft":
                await self._handle_draft_update(sender, message)
            elif msg_type == "state.request":
                # [advice from AI] 클라이언트가 현재 상태 요청 (초기 연결 시 메시지 손실 방지)
                await self._handle_state_request(sender)
            elif msg_type == "stt.start":
                # [advice from AI] STT 시작 요청
                await self._handle_stt_start(sender)
            elif msg_type == "stt.stop":
                # [advice from AI] STT 중지 요청
                await self._handle_stt_stop(sender)
            else:
                logger.debug(f"[RoomAgent] 알 수 없는 메시지 타입: {msg_type}")
                
        except json.JSONDecodeError:
            logger.debug("[RoomAgent] JSON 파싱 실패, MessageHandler로 위임")
        except Exception as e:
            logger.error(f"[RoomAgent] 메시지 처리 오류: {e}")
    
    async def _handle_broadcast_request(self, sender: str, message: dict) -> None:
        """
        [advice from AI] 송출 요청 처리
        
        송출 권한이 있는 속기사만 송출 가능.
        송출 후 다음 속기사에게 턴 전환.
        """
        text = message.get("text", "")
        
        if not self.turn_manager.has_permission(sender):
            logger.warning(f"[RoomAgent] 송출 권한 없음: {sender}")
            return
        
        logger.info(f"[RoomAgent] 송출 요청: {sender}, text={text[:50]}...")
        
        # 1. 송출 텍스트 누적 저장 (중앙 관리)
        # [advice from AI] 구분자 없이 append, 줄바꿈/공백은 속기사가 처리
        self._broadcast_text += text
        
        # 2. 송출 텍스트 브로드캐스트 (모든 참가자에게)
        # [advice from AI] 누적된 전체 텍스트를 전송
        await self._send_raw_message({
            "type": "caption.broadcast",
            "text": self._broadcast_text,
            "sender": sender,
        })
        
        # 3. 송출자의 입력 텍스트 초기화
        self._stenographer_texts[sender] = ""
        
        # 4. 외부 시스템에 전송 (방송국 등)
        current_ts = self.get_current_timestamp()
        await self.external_connector.send_caption_to_broadcast(text, current_ts)
        
        # 5. 턴 전환 (다음 속기사에게) - 현재 송출자 제외
        # [advice from AI] request_turn_switch를 사용하여 현재 보유자를 exclude
        await self.turn_manager.request_turn_switch(sender, current_ts)
        await self._broadcast_turn_state()
        
        # 6. 업데이트된 속기사 목록 브로드캐스트 (입력 텍스트 초기화 반영)
        await self._broadcast_stenographer_list()
        
        # 7. [advice from AI] Redis에 송출 이력 저장
        if redis_client and redis_client.is_connected:
            try:
                await redis_client.add_broadcast_history(
                    self.room_name,
                    {
                        "text": text,
                        "sender": sender,
                        "timestamp": current_ts,
                    }
                )
            except Exception as e:
                logger.debug(f"[RoomAgent] Redis 이력 저장 실패: {e}")
    
    async def _handle_draft_update(self, sender: str, message: dict) -> None:
        """
        [advice from AI] 임시 텍스트 업데이트 처리
        
        속기사별 텍스트 상태 저장 후 모든 참가자에게 브로드캐스트.
        """
        text = message.get("text", "")
        
        # 1. 속기사별 텍스트 상태 저장 (중앙 관리)
        self._stenographer_texts[sender] = text
        
        # 2. 모든 참가자에게 재브로드캐스트 (발신자 정보 포함)
        await self._send_raw_message({
            "type": "caption.draft",
            "text": text,
            "sender": sender,
        })
    
    async def _handle_state_request(self, sender: str) -> None:
        """
        [advice from AI] 클라이언트 상태 요청 처리
        
        클라이언트가 연결 후 현재 상태를 요청할 때 호출.
        속기사 목록, 턴 상태, 송출 텍스트를 전송.
        """
        logger.info(f"[RoomAgent] 상태 요청: {sender}")
        
        # 1. 속기사 목록 전송
        await self._broadcast_stenographer_list()
        
        # 2. 턴 상태 전송
        await self._broadcast_turn_state()
        
        # 3. 송출 텍스트 전송 (있으면)
        if self._broadcast_text:
            await self._send_raw_message({
                "type": "caption.broadcast",
                "text": self._broadcast_text,
                "sender": "system",
            })
        
        # 4. STT 상태 전송
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": self._stt_enabled,
        })
    
    def _get_ingress_audio_track(self) -> Optional["rtc.Track"]:
        """
        [advice from AI] Ingress 오디오 트랙 찾기
        
        Room의 참가자 목록에서 Ingress의 오디오 트랙을 찾아 반환.
        트랙 객체를 저장하지 않고 필요할 때마다 찾는 방식으로 크래시 방지.
        """
        if not self.room:
            return None
        
        for participant in self.room.remote_participants.values():
            if participant.identity == self.INGRESS_IDENTITY:
                for publication in participant.track_publications.values():
                    if (
                        publication.track 
                        and publication.track.kind == rtc.TrackKind.KIND_AUDIO
                    ):
                        return publication.track
        return None
    
    async def _handle_stt_start(self, sender: str) -> None:
        """
        [advice from AI] STT 시작 요청 처리
        """
        logger.info(f"[RoomAgent] STT 시작 요청: {sender}")
        
        if self._stt_enabled:
            logger.warning("[RoomAgent] STT 이미 실행 중")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": True,
                "message": "already_running",
            })
            return
        
        # [advice from AI] 동적으로 트랙 찾기 (저장된 참조 대신)
        audio_track = self._get_ingress_audio_track()
        if not audio_track:
            logger.warning("[RoomAgent] Ingress 오디오 트랙 없음")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": False,
                "message": "no_audio_track",
            })
            return
        
        # [advice from AI] lazy 생성: STT 시작 시점에 커넥터 생성
        connector = self._get_or_create_stt_connector()
        if not connector:
            logger.warning("[RoomAgent] STT Connector 생성 실패")
            await self._send_raw_message({
                "type": "stt.status",
                "enabled": False,
                "message": "stt_disabled",
            })
            return
        
        # STT 시작
        self._stt_stream_task = asyncio.create_task(
            self._start_stt_with_audio_track(audio_track)
        )
        
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": True,
            "message": "started",
        })
    
    async def _handle_stt_stop(self, sender: str) -> None:
        """
        [advice from AI] STT 중지 요청 처리
        """
        logger.info(f"[RoomAgent] STT 중지 요청: {sender}")
        
        if self._stt_stream_task:
            self._stt_stream_task.cancel()
            try:
                await self._stt_stream_task
            except asyncio.CancelledError:
                pass
            self._stt_stream_task = None
        
        await self.stop_stt()
        
        await self._send_raw_message({
            "type": "stt.status",
            "enabled": False,
            "message": "stopped",
        })
    
    async def start_turn(self, holder_identity: str) -> Optional[Turn]:
        """
        턴 시작 (API)
        
        지정된 속기사에게 턴 권한을 부여한다.
        
        Args:
            holder_identity: 속기사 identity
            
        Returns:
            생성된 Turn 객체
        """
        current_ts = self.get_current_timestamp()
        return await self.turn_manager.start_turn(holder_identity, current_ts)
    
    async def switch_turn(
        self,
        next_holder: Optional[str] = None,
    ) -> bool:
        """
        턴 전환 (API)
        
        Args:
            next_holder: 다음 턴 보유자 (None이면 자동 선택)
            
        Returns:
            성공 여부
        """
        current_ts = self.get_current_timestamp()
        result = await self.turn_manager.switch_turn(next_holder, current_ts)
        return result.success
    
    def has_turn_permission(self, identity: str) -> bool:
        """턴 권한 확인"""
        return self.turn_manager.has_permission(identity)
    
    async def stop(self) -> None:
        """RoomAgent 중지 및 리소스 정리"""
        logger.info(f"[RoomAgent] 중지: room={self.room_name}")
        
        self.state = AgentState.SHUTTING_DOWN
        
        # [advice from AI] STT 정리
        await self.stop_stt()
        
        await self.message_handler.stop()
        await self.turn_manager.stop()
        await self.caption_manager.stop()
        await self.external_connector.stop()
        
        # [advice from AI] Redis 상태 정리 (이력은 유지)
        if redis_client and redis_client.is_connected:
            try:
                await redis_client.delete_room_state(self.room_name)
            except Exception as e:
                logger.debug(f"[RoomAgent] Redis 정리 실패: {e}")
        
        self.room = None
        
        logger.info("[RoomAgent] 리소스 정리 완료")
    
    def get_current_timestamp(self) -> int:
        """현재 영상 타임스탬프 (밀리초)"""
        return int(time.time() * 1000) - self._start_time_ms
    
    def get_delayed_timestamp(self) -> int:
        """지연된 영상 타임스탬프 (밀리초)"""
        return max(0, self.get_current_timestamp() - self.delay_ms)
    
    def get_captions_in_range(
        self,
        start_ms: int,
        end_ms: int,
    ) -> List[CaptionSegment]:
        """시간 범위 내 자막 조회"""
        return self.caption_manager.get_segments_in_range(start_ms, end_ms)
    
    def get_merged_caption(self, turn_id: str) -> Optional[MergedCaption]:
        """병합된 자막 조회"""
        return self.caption_manager.get_merged_caption(turn_id)
    
    async def send_caption_to_broadcast(
        self,
        caption_text: str,
        timestamp_ms: int,
    ) -> bool:
        """방송국에 자막 전송"""
        return await self.external_connector.send_caption_to_broadcast(
            caption_text=caption_text,
            timestamp_ms=timestamp_ms,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Agent 상태 정보"""
        return {
            "room_name": self.room_name,
            "state": self.state.value,
            "agent_identity": self.agent_identity,
            "delay_ms": self.delay_ms,
            "turn_manager": self.turn_manager.get_stats(),
            "caption_manager": self.caption_manager.get_stats(),
            "external_connector": self.external_connector.get_stats(),
        }
