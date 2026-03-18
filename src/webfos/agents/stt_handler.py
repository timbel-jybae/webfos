"""
STT Handler - STT 처리 전담 모듈.

RoomAgent에서 분리된 STT 관련 로직을 담당합니다.
- STT Connector 관리
- 텍스트 추출 및 처리
- 오디오 리샘플링
- 편집 모드 관리

[advice from AI] RoomAgent 리팩토링 Phase 1
"""

import asyncio
import math
import struct
import array
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from loguru import logger

from core.config import settings

if TYPE_CHECKING:
    from livekit import rtc
    from .stt_connector import STTConnector


class STTHandler:
    """
    STT 처리 핸들러.
    
    STT 연결, 텍스트 처리, 오디오 리샘플링 등을 담당합니다.
    RoomAgent와 협력하여 동작하며, 필요한 콜백과 상태를 주입받습니다.
    """
    
    def __init__(
        self,
        get_current_holder: Callable[[], Optional[str]],
        send_to_participant: Callable[[dict, str], Awaitable[bool]],
        get_current_timestamp: Callable[[], int],
    ):
        """
        Args:
            get_current_holder: 현재 턴 보유자 identity 반환 함수
            send_to_participant: 특정 참가자에게 메시지 전송 함수
            get_current_timestamp: 현재 타임스탬프 반환 함수
        """
        # [advice from AI] 콜백 함수 (RoomAgent와 협력)
        self._get_current_holder = get_current_holder
        self._send_to_participant = send_to_participant
        self._get_current_timestamp = get_current_timestamp
        
        # [advice from AI] STT 상태 관리
        self._stt_enabled: bool = False
        self._stt_partial_text: str = ""  # 레거시, 하위 호환용
        self._stt_connector: Optional["STTConnector"] = None
        self._stt_stream_task: Optional[asyncio.Task] = None
        self._stt_last_final_text: str = ""  # 마지막으로 전송한 final 텍스트 (중복 방지)
        
        # [advice from AI] STT 텍스트 상태 관리 (RoomAgent가 직접 타이핑하는 것처럼)
        self._stt_confirmed_text: str = ""  # 확정된 텍스트 (final)
        self._stt_typing_text: str = ""     # 현재 입력 중 텍스트 (partial)
        
        # [advice from AI] 편집 모드 상태 관리
        self._edit_mode: bool = False
        self._editor_identity: str = ""
        self._stt_temp_buffer: str = ""  # 편집 중 STT 임시 저장 버퍼
        
        # [advice from AI] 턴 전환 플래그 (STT 콜백에서 브로드캐스트 차단용)
        self._turn_switching: bool = False
        
        logger.info("[STTHandler] 초기화 완료")
    
    def _get_or_create_stt_connector(self):
        """
        [advice from AI] STT Connector lazy 생성 및 lazy import
        
        STTConnector import 자체가 LiveKit SDK와 충돌할 수 있으므로
        실제 필요 시점에만 import
        """
        if self._stt_connector:
            return self._stt_connector
        
        if not settings.STT_ENABLED:
            logger.info("[STTHandler] STT 비활성화 (config)")
            return None
        
        # [advice from AI] Lazy import - 실제 사용 시점에만 import
        try:
            from .stt_connector import STTConnector as STTConnectorClass
            logger.info("[STTHandler] STTConnector import 성공")
        except ImportError as e:
            logger.error(f"[STTHandler] STTConnector import 실패: {e}")
            return None
        except Exception as e:
            logger.error(f"[STTHandler] STTConnector import 예외: {e}")
            return None
        
        try:
            self._stt_connector = STTConnectorClass(
                model=settings.STT_MODEL,
                language=settings.STT_LANGUAGE,
                use_vad=True,
                on_partial=self._on_stt_partial,
                on_final=self._on_stt_final,
            )
            logger.info(f"[STTHandler] STT Connector 생성: {settings.STT_MODEL}")
            return self._stt_connector
        except Exception as e:
            logger.error(f"[STTHandler] STT Connector 생성 예외: {e}")
            return None
    
    def _extract_new_text(self, current_text: str, previous_text: str) -> str:
        """
        [advice from AI] 이전 텍스트와 비교하여 새로운 부분만 추출
        
        WhisperLive는 전체 컨텍스트를 반환하므로, 이전에 이미 전송한 부분을 제외하고
        새롭게 추가된 부분만 추출합니다.
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
        """
        # 턴 전환 중이면 브로드캐스트 스킵
        if self._turn_switching:
            logger.debug("[STTHandler] STT partial 스킵: 턴 전환 중")
            return
        
        # 새로운 부분만 추출
        new_text = self._extract_new_text(text, self._stt_last_final_text)
        
        if not new_text:
            return
        
        # 편집 모드 분기
        if self._edit_mode:
            self._stt_typing_text = new_text
            logger.debug(f"[STTHandler] STT partial (편집 모드): {new_text[:50]}...")
        else:
            self._stt_typing_text = new_text
            self._stt_partial_text = new_text  # 하위 호환
            
            await self._broadcast_stt_text()
            logger.debug(f"[STTHandler] STT partial: {new_text[:50]}...")
    
    async def _on_stt_final(self, text: str, segments: list) -> None:
        """
        [advice from AI] STT 최종 결과 콜백
        """
        # 턴 전환 중이면 last_final_text만 갱신
        if self._turn_switching:
            self._stt_last_final_text = text
            logger.debug("[STTHandler] STT final 스킵: 턴 전환 중")
            return
        
        # 새로운 부분만 추출
        new_text = self._extract_new_text(text, self._stt_last_final_text)
        
        if not new_text:
            return
        
        # 편집 모드 분기
        if self._edit_mode:
            self._stt_temp_buffer += new_text
            self._stt_typing_text = ""
            logger.info(f"[STTHandler] STT final (편집 모드): {new_text[:50]}...")
        else:
            self._stt_confirmed_text += new_text
            self._stt_typing_text = ""
            self._stt_partial_text = ""
            
            await self._broadcast_stt_text()
            logger.info(f"[STTHandler] STT final: {new_text[:50]}...")
        
        # 마지막 final 텍스트 갱신
        self._stt_last_final_text = text
    
    async def _broadcast_stt_text(self) -> None:
        """
        [advice from AI] STT 텍스트 상태를 현재 턴 보유자에게만 전송
        """
        current_holder = self._get_current_holder()
        
        if not current_holder:
            logger.debug("[STTHandler] STT 텍스트 전송 스킵: 턴 보유자 없음")
            return
        
        message = {
            "type": "stt.text",
            "confirmed": self._stt_confirmed_text,
            "typing": self._stt_typing_text,
            "timestamp": self._get_current_timestamp(),
        }
        
        await self._send_to_participant(message, current_holder)
        
        logger.debug(
            f"[STTHandler] STT 텍스트 전송 to {current_holder}: "
            f"confirmed={len(self._stt_confirmed_text)}자, "
            f"typing={len(self._stt_typing_text)}자"
        )
    
    async def reset_stt_text_state(self) -> None:
        """
        [advice from AI] STT 텍스트 상태 초기화 (송출/턴 전환 시)
        """
        self._stt_confirmed_text = ""
        self._stt_typing_text = ""
        self._stt_temp_buffer = ""
        # _stt_last_final_text 유지 (중복 방지용)
        self._edit_mode = False
        self._editor_identity = ""
        
        logger.info("[STTHandler] STT 텍스트 상태 초기화 완료")
    
    async def start_stt(self) -> bool:
        """
        [advice from AI] STT 시작
        """
        connector = self._get_or_create_stt_connector()
        if not connector:
            logger.warning("[STTHandler] STT Connector 없음")
            return False
        
        if self._stt_enabled:
            logger.warning("[STTHandler] STT 이미 실행 중")
            return True
        
        success = await connector.connect()
        if success:
            self._stt_enabled = True
            self._stt_last_final_text = ""
            self._stt_confirmed_text = ""
            self._stt_typing_text = ""
            self._stt_temp_buffer = ""
            self._edit_mode = False
            self._editor_identity = ""
            logger.info("[STTHandler] STT 시작됨")
        
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
        self._stt_last_final_text = ""
        self._stt_confirmed_text = ""
        self._stt_typing_text = ""
        self._stt_temp_buffer = ""
        self._edit_mode = False
        self._editor_identity = ""
        logger.info("[STTHandler] STT 중지됨")
    
    @property
    def stt_enabled(self) -> bool:
        """STT 활성화 여부"""
        return self._stt_enabled
    
    @property
    def stt_connector(self):
        """STT Connector 인스턴스"""
        return self._stt_connector
    
    @property
    def confirmed_text(self) -> str:
        """확정된 STT 텍스트"""
        return self._stt_confirmed_text
    
    @property
    def typing_text(self) -> str:
        """입력 중인 STT 텍스트"""
        return self._stt_typing_text
    
    @property
    def temp_buffer(self) -> str:
        """편집 모드 임시 버퍼"""
        return self._stt_temp_buffer
    
    @property
    def edit_mode(self) -> bool:
        """편집 모드 여부"""
        return self._edit_mode
    
    @property
    def editor_identity(self) -> str:
        """현재 편집자 identity"""
        return self._editor_identity
    
    def set_turn_switching(self, switching: bool) -> None:
        """턴 전환 플래그 설정"""
        self._turn_switching = switching
        logger.info(f"[STTHandler] 턴 전환 플래그: {switching}")
    
    def start_edit_mode(self, editor: str) -> bool:
        """
        편집 모드 시작
        
        Returns:
            성공 여부 (다른 사람이 편집 중이면 False)
        """
        if self._edit_mode and self._editor_identity != editor:
            logger.warning(f"[STTHandler] 편집 모드 시작 거부: 이미 {self._editor_identity}가 편집 중")
            return False
        
        self._edit_mode = True
        self._editor_identity = editor
        logger.info(f"[STTHandler] 편집 모드 시작: {editor}")
        return True
    
    def end_edit_mode(self, editor: str, edited_text: str) -> Optional[str]:
        """
        편집 모드 종료 및 텍스트 병합
        
        Args:
            editor: 편집 종료한 속기사 identity
            edited_text: 편집된 텍스트
        
        Returns:
            병합된 텍스트 (실패 시 None)
        """
        if not self._edit_mode:
            logger.warning("[STTHandler] 편집 모드 종료 거부: 편집 모드 아님")
            return None
        
        if self._editor_identity != editor:
            logger.warning(f"[STTHandler] 편집 모드 종료 거부: {editor}는 편집자가 아님")
            return None
        
        # 텍스트 병합: 편집된 텍스트 + 임시 버퍼
        merged_text = edited_text
        if self._stt_temp_buffer:
            merged_text = edited_text + self._stt_temp_buffer
            logger.info(f"[STTHandler] 텍스트 병합: 편집={len(edited_text)}자 + 버퍼={len(self._stt_temp_buffer)}자")
        
        # 상태 초기화
        self._stt_temp_buffer = ""
        self._edit_mode = False
        self._editor_identity = ""
        
        # 확정 텍스트 갱신
        self._stt_confirmed_text = merged_text
        self._stt_typing_text = ""
        
        logger.info(f"[STTHandler] 편집 모드 종료: 병합={len(merged_text)}자")
        return merged_text
    
    async def start_stt_with_audio_track(self, track: "rtc.Track") -> None:
        """
        [advice from AI] 오디오 트랙과 함께 STT 시작
        """
        from livekit import rtc
        
        if not await self.start_stt():
            logger.error("[STTHandler] STT 시작 실패")
            return
        
        logger.info("[STTHandler] 오디오 트랙 STT 처리 시작")
        
        # 오디오 버퍼링 및 리샘플링 설정
        audio_buffer = bytearray()
        target_sample_rate = 16000
        buffer_duration_ms = 100
        min_rms_threshold = 50
        
        frame_count = 0
        source_sample_rate = None
        sent_chunks = 0
        rms_filtered = 0
        
        try:
            try:
                audio_stream = rtc.AudioStream(track)
                logger.info("[STTHandler] AudioStream 생성 성공")
            except Exception as stream_err:
                logger.error(f"[STTHandler] AudioStream 생성 실패: {stream_err}")
                await self.stop_stt()
                return
            
            async for frame_event in audio_stream:
                if not self._stt_enabled:
                    logger.info("[STTHandler] STT 비활성화 -> 오디오 루프 종료")
                    break
                
                frame = frame_event.frame
                
                if frame_count == 0:
                    source_sample_rate = frame.sample_rate
                    logger.info(
                        f"[STTHandler] 첫 오디오 프레임 수신: rate={source_sample_rate}Hz, "
                        f"ch={frame.num_channels}, samples={frame.samples_per_channel}"
                    )
                
                frame_count += 1
                audio_data = frame.data.tobytes()
                
                if source_sample_rate and source_sample_rate != target_sample_rate:
                    audio_data = self._resample_audio(
                        audio_data, source_sample_rate, target_sample_rate, frame.num_channels
                    )
                
                audio_buffer.extend(audio_data)
                
                buffer_size = target_sample_rate * 2 * buffer_duration_ms // 1000
                if len(audio_buffer) >= buffer_size:
                    chunk = bytes(audio_buffer[:buffer_size])
                    audio_buffer = audio_buffer[buffer_size:]
                    
                    rms = self._calculate_rms(chunk)
                    if rms > min_rms_threshold:
                        await self._stt_connector.send_audio(chunk)
                        sent_chunks += 1
                    else:
                        rms_filtered += 1
                
                if frame_count % 500 == 0:
                    logger.info(
                        f"[STTHandler] 오디오 통계: frames={frame_count}, "
                        f"sent={sent_chunks}, rms_filtered={rms_filtered}, "
                        f"connector={self._stt_connector.state.value if self._stt_connector else 'none'}"
                    )
                
        except asyncio.CancelledError:
            logger.info("[STTHandler] 오디오 스트림 취소됨")
        except Exception as e:
            logger.error(f"[STTHandler] 오디오 스트림 처리 오류: {e}", exc_info=True)
        finally:
            logger.info(
                f"[STTHandler] 오디오 트랙 STT 처리 종료: "
                f"frames={frame_count}, sent={sent_chunks}, rms_filtered={rms_filtered}"
            )
    
    def _resample_audio(
        self, 
        audio_data: bytes, 
        source_rate: int, 
        target_rate: int,
        num_channels: int
    ) -> bytes:
        """
        [advice from AI] 오디오 리샘플링 (간단한 선형 보간)
        """
        # int16 샘플로 변환
        num_samples = len(audio_data) // 2
        samples = struct.unpack(f'<{num_samples}h', audio_data)
        
        # 스테레오면 모노로 변환
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
        [advice from AI] 오디오 RMS 계산
        """
        num_samples = len(audio_data) // 2
        if num_samples == 0:
            return 0
        
        samples = struct.unpack(f'<{num_samples}h', audio_data)
        sum_squares = sum(s * s for s in samples)
        rms = math.sqrt(sum_squares / num_samples)
        
        return rms
