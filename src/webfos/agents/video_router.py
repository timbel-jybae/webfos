"""
영상 스트림 라우팅 모듈.

HLS Ingress로 수신된 영상 스트림을 역할에 따라 라우팅한다:
- 속기사: 실시간 스트림 (Ingress 트랙 직접 구독)
- 검수자: 지연 스트림 (RingBuffer를 통한 지연 트랙)
"""

import asyncio
from typing import Optional, Tuple, Any, Deque
from collections import deque
from dataclasses import dataclass, field
import time

from loguru import logger

try:
    from livekit import rtc
except ImportError:
    rtc = None


@dataclass
class BufferedFrame:
    """
    버퍼에 저장되는 프레임 데이터
    
    Attributes:
        frame: 비디오/오디오 프레임 객체
        timestamp_ms: 프레임 타임스탬프 (밀리초)
        received_at: 수신 시각 (Unix timestamp)
    """
    frame: Any
    timestamp_ms: int
    received_at: float = field(default_factory=time.time)


class FrameRingBuffer:
    """
    고정 시간 윈도우 기반 프레임 링 버퍼.
    
    지정된 시간(max_duration_ms) 이내의 프레임만 유지하고,
    오래된 프레임은 자동으로 삭제(LRU)한다.
    
    Attributes:
        max_duration_ms: 버퍼 유지 시간 (밀리초)
    
    Example:
        buffer = FrameRingBuffer(max_duration_ms=4000)
        await buffer.push(frame, timestamp_ms=1000)
        delayed_frame = await buffer.read_delayed(delay_ms=3500)
    """
    
    def __init__(self, max_duration_ms: int = 4000):
        """
        Args:
            max_duration_ms: 버퍼 유지 시간 (밀리초)
        """
        self.max_duration_ms = max_duration_ms
        self._buffer: Deque[BufferedFrame] = deque()
        self._lock = asyncio.Lock()
        self._frame_count = 0
        self._dropped_count = 0
    
    async def push(self, frame: Any, timestamp_ms: int) -> None:
        """
        프레임 추가
        
        프레임을 버퍼에 추가하고, 오래된 프레임을 자동으로 정리한다.
        
        Args:
            frame: 비디오/오디오 프레임 객체
            timestamp_ms: 프레임 타임스탬프 (밀리초)
        """
        async with self._lock:
            now = time.time()
            buffered = BufferedFrame(
                frame=frame,
                timestamp_ms=timestamp_ms,
                received_at=now,
            )
            self._buffer.append(buffered)
            self._frame_count += 1
            
            self._cleanup_old_frames()
    
    def _cleanup_old_frames(self) -> None:
        """
        오래된 프레임 정리 (LRU)
        
        현재 시간 기준으로 max_duration_ms보다 오래된 프레임을 제거한다.
        _lock이 획득된 상태에서 호출되어야 한다.
        """
        if not self._buffer:
            return
        
        now_ms = int(time.time() * 1000)
        newest_ts = self._buffer[-1].timestamp_ms if self._buffer else now_ms
        cutoff_ts = newest_ts - self.max_duration_ms
        
        while self._buffer and self._buffer[0].timestamp_ms < cutoff_ts:
            self._buffer.popleft()
            self._dropped_count += 1
    
    async def read_delayed(self, delay_ms: int) -> Optional[BufferedFrame]:
        """
        지연된 프레임 읽기
        
        현재 시간에서 delay_ms만큼 이전 시점의 프레임을 반환한다.
        해당 시점의 프레임이 없으면 None을 반환한다.
        
        Args:
            delay_ms: 지연 시간 (밀리초)
            
        Returns:
            BufferedFrame 또는 None
        """
        async with self._lock:
            if not self._buffer:
                return None
            
            newest_ts = self._buffer[-1].timestamp_ms
            target_ts = newest_ts - delay_ms
            
            best_match: Optional[BufferedFrame] = None
            min_diff = float('inf')
            
            for buffered in self._buffer:
                diff = abs(buffered.timestamp_ms - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    best_match = buffered
                if buffered.timestamp_ms > target_ts:
                    break
            
            return best_match
    
    async def read_delayed_and_remove(self, delay_ms: int) -> Optional[BufferedFrame]:
        """
        지연된 프레임 읽기 및 제거
        
        read_delayed와 동일하지만, 읽은 프레임 이전의 모든 프레임을 제거한다.
        연속 스트리밍 출력에 적합하다.
        
        Args:
            delay_ms: 지연 시간 (밀리초)
            
        Returns:
            BufferedFrame 또는 None
        """
        async with self._lock:
            if not self._buffer:
                return None
            
            newest_ts = self._buffer[-1].timestamp_ms
            target_ts = newest_ts - delay_ms
            
            result: Optional[BufferedFrame] = None
            
            while self._buffer:
                if self._buffer[0].timestamp_ms <= target_ts:
                    result = self._buffer.popleft()
                else:
                    break
            
            return result
    
    async def peek_oldest(self) -> Optional[BufferedFrame]:
        """가장 오래된 프레임 조회 (제거하지 않음)"""
        async with self._lock:
            if self._buffer:
                return self._buffer[0]
            return None
    
    async def peek_newest(self) -> Optional[BufferedFrame]:
        """가장 최신 프레임 조회 (제거하지 않음)"""
        async with self._lock:
            if self._buffer:
                return self._buffer[-1]
            return None
    
    async def get_buffer_duration_ms(self) -> int:
        """
        현재 버퍼에 저장된 시간 범위 (밀리초)
        
        Returns:
            최신 프레임과 가장 오래된 프레임 사이의 시간 차이
        """
        async with self._lock:
            if len(self._buffer) < 2:
                return 0
            return self._buffer[-1].timestamp_ms - self._buffer[0].timestamp_ms
    
    async def size(self) -> int:
        """현재 버퍼 크기 (프레임 수)"""
        async with self._lock:
            return len(self._buffer)
    
    async def clear(self) -> None:
        """버퍼 초기화"""
        async with self._lock:
            self._buffer.clear()
    
    def get_stats(self) -> dict:
        """버퍼 통계 정보"""
        return {
            "frame_count": self._frame_count,
            "dropped_count": self._dropped_count,
            "current_size": len(self._buffer),
            "max_duration_ms": self.max_duration_ms,
        }


class VideoRouter:
    """
    영상 스트림 라우팅 관리
    
    Ingress 트랙을 수신하여:
    1. 실시간 트랙: 속기사가 직접 Ingress 트랙을 구독
    2. 지연 트랙: RingBuffer를 통해 지연된 트랙을 검수자에게 제공
    
    Attributes:
        delay_ms: 검수자용 지연 시간 (밀리초)
        buffer_margin_ms: 버퍼 여유 시간 (밀리초)
        fps: 비디오 프레임 레이트
    """
    
    def __init__(
        self,
        delay_ms: int = 3500,
        buffer_margin_ms: int = 1000,
        fps: int = 30,
    ):
        """
        Args:
            delay_ms: 검수자용 지연 시간 (밀리초)
            buffer_margin_ms: 버퍼 여유 시간 (밀리초)
            fps: 비디오 프레임 레이트
        """
        self.delay_ms = delay_ms
        self.buffer_margin_ms = buffer_margin_ms
        self.fps = fps
        
        buffer_duration = delay_ms + buffer_margin_ms
        self.video_buffer = FrameRingBuffer(max_duration_ms=buffer_duration)
        self.audio_buffer = FrameRingBuffer(max_duration_ms=buffer_duration)
        
        self._is_running = False
        self._tasks: list = []
        
        self._video_source: Optional[Any] = None
        self._audio_source: Optional[Any] = None
        self._delayed_video_track: Optional[Any] = None
        self._delayed_audio_track: Optional[Any] = None
        
        self._base_timestamp_ms: Optional[int] = None
        self._current_timestamp_ms: int = 0
        
        # [advice from AI] 오디오 설정을 동적으로 감지하기 위한 플래그
        self._audio_source_initialized = False
        self._room: Optional[Any] = None
        
        logger.info(
            f"[VideoRouter] 초기화: delay={delay_ms}ms, "
            f"buffer={buffer_duration}ms, fps={fps}, resolution=720p"
        )
    
    async def start(
        self,
        room: "rtc.Room",
        ingress_video_track: "rtc.VideoTrack",
        ingress_audio_track: "rtc.AudioTrack",
        delayed_identity: str = "room-agent-delayed",
    ) -> None:
        """
        영상 라우팅 시작
        
        지연 트랙을 생성하고 Room에 publish한 후,
        Ingress 트랙 버퍼링 및 지연 출력을 시작한다.
        
        Args:
            room: LiveKit Room 인스턴스
            ingress_video_track: Ingress 비디오 트랙
            ingress_audio_track: Ingress 오디오 트랙
            delayed_identity: 지연 트랙 identity
        """
        if self._is_running:
            logger.warning("[VideoRouter] 이미 실행 중")
            return
        
        if rtc is None:
            logger.error("[VideoRouter] livekit 모듈을 찾을 수 없음")
            return
        
        self._is_running = True
        logger.info("[VideoRouter] 영상 라우팅 시작")
        
        try:
            self._room = room
            
            # [advice from AI] VideoSource는 width, height만 지원
            # frame_rate는 출력 루프에서 제어
            # 720p로 메모리 사용량 감소 (1080p 대비 ~55% 감소)
            self._video_source = rtc.VideoSource(
                width=1280,
                height=720,
            )
            
            self._delayed_video_track = rtc.LocalVideoTrack.create_video_track(
                "delayed-video",
                self._video_source,
            )
            
            video_options = rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_CAMERA,
            )
            
            await room.local_participant.publish_track(
                self._delayed_video_track,
                video_options,
            )
            
            logger.info(f"[VideoRouter] 비디오 트랙 publish 완료: {delayed_identity}")
            
            # [advice from AI] 오디오 소스는 첫 프레임 수신 시 동적으로 생성
            # (sample_rate, num_channels를 실제 프레임에서 감지)
            self._audio_source_initialized = False
            
            self._tasks = [
                asyncio.create_task(self._buffer_video(ingress_video_track)),
                asyncio.create_task(self._buffer_audio(ingress_audio_track)),
                asyncio.create_task(self._output_delayed_video()),
                asyncio.create_task(self._output_delayed_audio()),
            ]
            
        except Exception as e:
            logger.error(f"[VideoRouter] 시작 실패: {e}")
            self._is_running = False
            raise
    
    async def stop(self) -> None:
        """
        영상 라우팅 중지 및 리소스 정리
        """
        if not self._is_running:
            return
        
        logger.info("[VideoRouter] 영상 라우팅 중지")
        self._is_running = False
        
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks.clear()
        
        await self.video_buffer.clear()
        await self.audio_buffer.clear()
        
        self._video_source = None
        self._audio_source = None
        self._delayed_video_track = None
        self._delayed_audio_track = None
        
        logger.info("[VideoRouter] 리소스 정리 완료")
    
    async def _buffer_video(self, track: "rtc.VideoTrack") -> None:
        """
        비디오 트랙 버퍼링 태스크
        
        Ingress 비디오 트랙에서 프레임을 수신하여 버퍼에 저장한다.
        [advice from AI] 프레임 데이터를 복사하여 저장 (원본 프레임은 스트림에서 재사용됨)
        """
        logger.info("[VideoRouter] 비디오 버퍼링 시작")
        
        try:
            stream = rtc.VideoStream(track)
            async for event in stream:
                if not self._is_running:
                    break
                
                frame = event.frame
                timestamp_ms = self._get_current_timestamp_ms()
                
                # 프레임 데이터 복사 (원본 프레임은 스트림에서 재사용되므로)
                frame_copy = rtc.VideoFrame(
                    width=frame.width,
                    height=frame.height,
                    type=frame.type,
                    data=bytes(frame.data),
                )
                
                await self.video_buffer.push(frame_copy, timestamp_ms)
                self._current_timestamp_ms = timestamp_ms
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[VideoRouter] 비디오 버퍼링 오류: {e}")
        finally:
            logger.info("[VideoRouter] 비디오 버퍼링 종료")
    
    async def _buffer_audio(self, track: "rtc.AudioTrack") -> None:
        """
        오디오 트랙 버퍼링 태스크
        
        Ingress 오디오 트랙에서 프레임을 수신하여 버퍼에 저장한다.
        [advice from AI] 첫 프레임 수신 시 AudioSource를 동적으로 생성한다.
        프레임 데이터를 복사하여 저장 (원본 프레임은 스트림에서 재사용됨)
        """
        logger.info("[VideoRouter] 오디오 버퍼링 시작")
        
        try:
            stream = rtc.AudioStream(track)
            async for event in stream:
                if not self._is_running:
                    break
                
                frame = event.frame
                timestamp_ms = self._get_current_timestamp_ms()
                
                # 첫 프레임에서 오디오 설정 감지 및 AudioSource 생성
                if not self._audio_source_initialized:
                    await self._initialize_audio_source(frame)
                
                # 프레임 데이터 복사 (원본 프레임은 스트림에서 재사용되므로)
                frame_copy = rtc.AudioFrame(
                    data=bytes(frame.data),
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                    samples_per_channel=frame.samples_per_channel,
                )
                
                await self.audio_buffer.push(frame_copy, timestamp_ms)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[VideoRouter] 오디오 버퍼링 오류: {e}")
        finally:
            logger.info("[VideoRouter] 오디오 버퍼링 종료")
    
    async def _initialize_audio_source(self, sample_frame: Any) -> None:
        """
        첫 오디오 프레임을 기반으로 AudioSource를 동적으로 생성하고 publish한다.
        """
        try:
            sample_rate = sample_frame.sample_rate
            num_channels = sample_frame.num_channels
            
            logger.info(
                f"[VideoRouter] 오디오 설정 감지: "
                f"sample_rate={sample_rate}, num_channels={num_channels}"
            )
            
            self._audio_source = rtc.AudioSource(
                sample_rate=sample_rate,
                num_channels=num_channels,
            )
            
            self._delayed_audio_track = rtc.LocalAudioTrack.create_audio_track(
                "delayed-audio",
                self._audio_source,
            )
            
            audio_options = rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_MICROPHONE,
            )
            
            await self._room.local_participant.publish_track(
                self._delayed_audio_track,
                audio_options,
            )
            
            self._audio_source_initialized = True
            logger.info("[VideoRouter] 오디오 트랙 publish 완료")
            
        except Exception as e:
            logger.error(f"[VideoRouter] AudioSource 초기화 실패: {e}")
    
    async def _output_delayed_video(self) -> None:
        """
        지연 비디오 출력 태스크
        
        버퍼에서 지연된 프레임을 읽어 지연 트랙으로 출력한다.
        """
        logger.info("[VideoRouter] 지연 비디오 출력 시작")
        frame_interval = 1.0 / self.fps
        
        await asyncio.sleep(self.delay_ms / 1000.0)
        
        try:
            while self._is_running:
                buffered = await self.video_buffer.read_delayed_and_remove(self.delay_ms)
                
                if buffered and self._video_source:
                    try:
                        # [advice from AI] VideoSource.capture_frame()은 동기 메서드
                        self._video_source.capture_frame(buffered.frame)
                    except Exception as e:
                        logger.debug(f"[VideoRouter] 비디오 프레임 출력 오류: {e}")
                
                await asyncio.sleep(frame_interval)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[VideoRouter] 지연 비디오 출력 오류: {e}")
        finally:
            logger.info("[VideoRouter] 지연 비디오 출력 종료")
    
    async def _output_delayed_audio(self) -> None:
        """
        지연 오디오 출력 태스크
        
        버퍼에서 지연된 오디오 프레임을 읽어 지연 트랙으로 출력한다.
        """
        logger.info("[VideoRouter] 지연 오디오 출력 시작")
        audio_interval = 0.01
        
        await asyncio.sleep(self.delay_ms / 1000.0)
        
        try:
            while self._is_running:
                # AudioSource가 초기화될 때까지 대기
                if not self._audio_source_initialized:
                    await asyncio.sleep(audio_interval)
                    continue
                
                buffered = await self.audio_buffer.read_delayed_and_remove(self.delay_ms)
                
                if buffered and self._audio_source:
                    try:
                        # [advice from AI] AudioSource.capture_frame()은 비동기 메서드
                        await self._audio_source.capture_frame(buffered.frame)
                    except Exception as e:
                        logger.debug(f"[VideoRouter] 오디오 프레임 출력 오류: {e}")
                
                await asyncio.sleep(audio_interval)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[VideoRouter] 지연 오디오 출력 오류: {e}")
        finally:
            logger.info("[VideoRouter] 지연 오디오 출력 종료")
    
    def _get_current_timestamp_ms(self) -> int:
        """
        현재 영상 타임스탬프 계산 (밀리초)
        
        첫 프레임 수신 시점을 기준으로 경과 시간을 계산한다.
        """
        now = time.time()
        
        if self._base_timestamp_ms is None:
            self._base_timestamp_ms = int(now * 1000)
        
        return int(now * 1000) - self._base_timestamp_ms
    
    def get_current_timestamp(self) -> int:
        """
        현재 영상 타임스탬프 반환 (밀리초)
        
        자막 동기화에 사용한다.
        """
        return self._current_timestamp_ms
    
    def get_delayed_timestamp(self) -> int:
        """
        지연된 영상 타임스탬프 반환 (밀리초)
        
        검수자 자막 동기화에 사용한다.
        """
        return max(0, self._current_timestamp_ms - self.delay_ms)
    
    def get_stats(self) -> dict:
        """라우터 통계 정보"""
        return {
            "is_running": self._is_running,
            "delay_ms": self.delay_ms,
            "current_timestamp_ms": self._current_timestamp_ms,
            "delayed_timestamp_ms": self.get_delayed_timestamp(),
            "video_buffer": self.video_buffer.get_stats(),
            "audio_buffer": self.audio_buffer.get_stats(),
        }
