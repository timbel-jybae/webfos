"""
외부 시스템 연동 모듈 (스켈레톤).

STT, OCR, 방송국 시스템과의 연동을 담당한다.
- STT 서비스: 음성 인식 결과 수신
- OCR 서비스: 화면 텍스트 감지 결과 수신
- 방송국 시스템: 최종 자막 전송

[TODO] 실제 구현은 Phase 6에서 진행
"""

import asyncio
from typing import Optional, Callable, Awaitable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from loguru import logger

from .models.caption import STTResult, OCRResult


class ConnectionState(Enum):
    """연결 상태"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ExternalServiceConfig:
    """외부 서비스 설정"""
    url: str
    timeout: float = 5.0
    enabled: bool = True
    api_key: Optional[str] = None
    
    def is_configured(self) -> bool:
        """설정 완료 여부"""
        return bool(self.url) and self.enabled


STTCallback = Callable[[STTResult], Awaitable[None]]
OCRCallback = Callable[[OCRResult], Awaitable[None]]


class ExternalConnector:
    """
    외부 시스템 연동 (스켈레톤)
    
    STT, OCR, 방송국 시스템과의 연동을 관리한다.
    
    Attributes:
        stt_config: STT 서비스 설정
        ocr_config: OCR 서비스 설정
        broadcast_config: 방송국 시스템 설정
    
    Example:
        connector = ExternalConnector(
            stt_url="http://stt-service/api",
            ocr_url="http://ocr-service/api",
            broadcast_url="http://broadcast-system/api",
        )
        await connector.start()
        ...
        await connector.stop()
    
    [TODO] 실제 WebSocket/HTTP 연결 구현
    """
    
    def __init__(
        self,
        stt_url: str = "",
        stt_timeout: float = 5.0,
        ocr_url: str = "",
        ocr_timeout: float = 5.0,
        broadcast_url: str = "",
        broadcast_timeout: float = 10.0,
    ):
        """
        Args:
            stt_url: STT 서비스 URL (빈 문자열이면 비활성화)
            stt_timeout: STT 서비스 타임아웃 (초)
            ocr_url: OCR 서비스 URL (빈 문자열이면 비활성화)
            ocr_timeout: OCR 서비스 타임아웃 (초)
            broadcast_url: 방송국 전송 URL (빈 문자열이면 비활성화)
            broadcast_timeout: 방송국 전송 타임아웃 (초)
        """
        self.stt_config = ExternalServiceConfig(
            url=stt_url,
            timeout=stt_timeout,
            enabled=bool(stt_url),
        )
        self.ocr_config = ExternalServiceConfig(
            url=ocr_url,
            timeout=ocr_timeout,
            enabled=bool(ocr_url),
        )
        self.broadcast_config = ExternalServiceConfig(
            url=broadcast_url,
            timeout=broadcast_timeout,
            enabled=bool(broadcast_url),
        )
        
        self._stt_state = ConnectionState.DISCONNECTED
        self._ocr_state = ConnectionState.DISCONNECTED
        self._broadcast_state = ConnectionState.DISCONNECTED
        
        self._stt_callbacks: List[STTCallback] = []
        self._ocr_callbacks: List[OCRCallback] = []
        
        self._is_running = False
        
        logger.info(
            f"[ExternalConnector] 초기화: "
            f"stt={'활성' if self.stt_config.enabled else '비활성'}, "
            f"ocr={'활성' if self.ocr_config.enabled else '비활성'}, "
            f"broadcast={'활성' if self.broadcast_config.enabled else '비활성'}"
        )
    
    async def start(self) -> None:
        """
        외부 연결 시작
        
        [TODO] 실제 연결 로직 구현
        - STT WebSocket 연결
        - OCR WebSocket 연결
        - 방송국 HTTP 연결 확인
        """
        if self._is_running:
            logger.warning("[ExternalConnector] 이미 실행 중")
            return
        
        self._is_running = True
        
        if self.stt_config.is_configured():
            await self._connect_stt()
        
        if self.ocr_config.is_configured():
            await self._connect_ocr()
        
        if self.broadcast_config.is_configured():
            await self._connect_broadcast()
        
        logger.info("[ExternalConnector] 시작")
    
    async def stop(self) -> None:
        """
        외부 연결 중지
        
        [TODO] 실제 연결 해제 로직 구현
        """
        if not self._is_running:
            return
        
        self._is_running = False
        
        await self._disconnect_stt()
        await self._disconnect_ocr()
        await self._disconnect_broadcast()
        
        logger.info("[ExternalConnector] 중지")
    
    async def _connect_stt(self) -> None:
        """
        STT 서비스 연결
        
        [TODO] WebSocket 연결 구현
        - 연결 설정
        - 메시지 수신 루프
        - 재연결 로직
        """
        self._stt_state = ConnectionState.CONNECTING
        logger.info(f"[ExternalConnector] STT 연결 시도: {self.stt_config.url}")
        
        # [TODO] 실제 WebSocket 연결
        # async with websockets.connect(self.stt_config.url) as ws:
        #     while self._is_running:
        #         data = await ws.recv()
        #         result = self._parse_stt_result(data)
        #         await self._fire_stt_callbacks(result)
        
        self._stt_state = ConnectionState.CONNECTED
        logger.info("[ExternalConnector] STT 연결 (스켈레톤)")
    
    async def _disconnect_stt(self) -> None:
        """STT 서비스 연결 해제"""
        if self._stt_state == ConnectionState.CONNECTED:
            # [TODO] 실제 연결 해제
            self._stt_state = ConnectionState.DISCONNECTED
            logger.info("[ExternalConnector] STT 연결 해제")
    
    async def _connect_ocr(self) -> None:
        """
        OCR 서비스 연결
        
        [TODO] WebSocket 연결 구현
        """
        self._ocr_state = ConnectionState.CONNECTING
        logger.info(f"[ExternalConnector] OCR 연결 시도: {self.ocr_config.url}")
        
        # [TODO] 실제 WebSocket 연결
        
        self._ocr_state = ConnectionState.CONNECTED
        logger.info("[ExternalConnector] OCR 연결 (스켈레톤)")
    
    async def _disconnect_ocr(self) -> None:
        """OCR 서비스 연결 해제"""
        if self._ocr_state == ConnectionState.CONNECTED:
            self._ocr_state = ConnectionState.DISCONNECTED
            logger.info("[ExternalConnector] OCR 연결 해제")
    
    async def _connect_broadcast(self) -> None:
        """
        방송국 시스템 연결 확인
        
        [TODO] HTTP 연결 확인 구현
        """
        self._broadcast_state = ConnectionState.CONNECTING
        logger.info(f"[ExternalConnector] 방송국 연결 확인: {self.broadcast_config.url}")
        
        # [TODO] 연결 확인 (health check)
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(f"{self.broadcast_config.url}/health") as resp:
        #         if resp.status == 200:
        #             self._broadcast_state = ConnectionState.CONNECTED
        
        self._broadcast_state = ConnectionState.CONNECTED
        logger.info("[ExternalConnector] 방송국 연결 (스켈레톤)")
    
    async def _disconnect_broadcast(self) -> None:
        """방송국 연결 해제"""
        if self._broadcast_state == ConnectionState.CONNECTED:
            self._broadcast_state = ConnectionState.DISCONNECTED
            logger.info("[ExternalConnector] 방송국 연결 해제")
    
    async def send_caption_to_broadcast(
        self,
        caption_text: str,
        timestamp_ms: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        방송국에 자막 전송
        
        Args:
            caption_text: 자막 텍스트
            timestamp_ms: 타임스탬프
            metadata: 추가 메타데이터
            
        Returns:
            전송 성공 여부
        
        [TODO] 실제 HTTP POST 구현
        """
        if not self.broadcast_config.is_configured():
            logger.debug("[ExternalConnector] 방송국 전송 비활성화")
            return False
        
        if self._broadcast_state != ConnectionState.CONNECTED:
            logger.warning("[ExternalConnector] 방송국 연결 안됨")
            return False
        
        logger.info(
            f"[ExternalConnector] 방송국 전송 (스켈레톤): "
            f"ts={timestamp_ms}ms, text_len={len(caption_text)}"
        )
        
        # [TODO] 실제 HTTP POST
        # payload = {
        #     "text": caption_text,
        #     "timestamp_ms": timestamp_ms,
        #     "metadata": metadata or {},
        # }
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(
        #         f"{self.broadcast_config.url}/caption",
        #         json=payload,
        #         timeout=self.broadcast_config.timeout,
        #     ) as resp:
        #         return resp.status == 200
        
        return True
    
    async def send_audio_to_stt(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> Optional[STTResult]:
        """
        오디오를 STT 서비스로 전송
        
        Args:
            audio_data: 오디오 바이트 데이터
            sample_rate: 샘플 레이트
            
        Returns:
            STT 결과 (동기 방식인 경우)
        
        [TODO] 실제 구현 (스트리밍 vs 배치)
        """
        if not self.stt_config.is_configured():
            return None
        
        logger.debug(
            f"[ExternalConnector] STT 전송 (스켈레톤): "
            f"audio_size={len(audio_data)} bytes"
        )
        
        # [TODO] 실제 전송
        return None
    
    async def send_frame_to_ocr(
        self,
        frame_data: bytes,
        timestamp_ms: int,
    ) -> Optional[OCRResult]:
        """
        프레임을 OCR 서비스로 전송
        
        Args:
            frame_data: 프레임 이미지 데이터
            timestamp_ms: 타임스탬프
            
        Returns:
            OCR 결과 (동기 방식인 경우)
        
        [TODO] 실제 구현
        """
        if not self.ocr_config.is_configured():
            return None
        
        logger.debug(
            f"[ExternalConnector] OCR 전송 (스켈레톤): "
            f"frame_size={len(frame_data)} bytes, ts={timestamp_ms}ms"
        )
        
        # [TODO] 실제 전송
        return None
    
    def on_stt_result(self, callback: STTCallback) -> None:
        """STT 결과 콜백 등록"""
        self._stt_callbacks.append(callback)
    
    def on_ocr_result(self, callback: OCRCallback) -> None:
        """OCR 결과 콜백 등록"""
        self._ocr_callbacks.append(callback)
    
    async def _fire_stt_callbacks(self, result: STTResult) -> None:
        """STT 콜백 실행"""
        for callback in self._stt_callbacks:
            try:
                await callback(result)
            except Exception as e:
                logger.error(f"[ExternalConnector] STT 콜백 오류: {e}")
    
    async def _fire_ocr_callbacks(self, result: OCRResult) -> None:
        """OCR 콜백 실행"""
        for callback in self._ocr_callbacks:
            try:
                await callback(result)
            except Exception as e:
                logger.error(f"[ExternalConnector] OCR 콜백 오류: {e}")
    
    def get_connection_states(self) -> Dict[str, str]:
        """연결 상태 조회"""
        return {
            "stt": self._stt_state.value,
            "ocr": self._ocr_state.value,
            "broadcast": self._broadcast_state.value,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보"""
        return {
            "stt_enabled": self.stt_config.enabled,
            "stt_url": self.stt_config.url if self.stt_config.enabled else None,
            "stt_state": self._stt_state.value,
            "ocr_enabled": self.ocr_config.enabled,
            "ocr_url": self.ocr_config.url if self.ocr_config.enabled else None,
            "ocr_state": self._ocr_state.value,
            "broadcast_enabled": self.broadcast_config.enabled,
            "broadcast_url": self.broadcast_config.url if self.broadcast_config.enabled else None,
            "broadcast_state": self._broadcast_state.value,
        }
