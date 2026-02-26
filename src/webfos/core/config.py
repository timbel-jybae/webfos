"""
Webfos 프로젝트 설정 — Pydantic Settings 기반.

환경변수 자동 로드, 타입 검증, 기본값 제공.
모든 레이어에서 `from core.config import settings`로 참조한다.

[advice from AI] VideoRouter 관련 설정 제거 (클라이언트 측 버퍼링 사용)
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):

    # === 기본 설정 ===
    PROJECT_NAME: str = "Webfos"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    DEBUG: bool = False

    # === 서버 설정 ===
    HOST: str = "0.0.0.0"
    PORT: int = 32055
    RELOAD: bool = False
    WORKERS: int = 1

    # === LiveKit 설정 ===
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_TIMEOUT: float = 10.0

    # === HLS 소스 설정 ===
    HLS_SOURCE_URL: str = "https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8"
    DEFAULT_ROOM_NAME: str = "webfos-room"

    # === 경로 설정 ===
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # === 로깅 ===
    LOG_LEVEL: str = "INFO"

    # === RoomAgent 설정 ===
    
    # 영상 지연 설정 (클라이언트 측 버퍼링 참조용)
    AGENT_DELAY_MS: int = 3500              # 검수자용 영상 지연 시간 (밀리초)
    
    # 턴 관리 설정 (TurnManager)
    AGENT_TURN_DURATION_MS: int = 30000     # 기본 턴 지속 시간 (밀리초, 자동 전환 시)
    AGENT_TURN_AUTO_SWITCH: bool = False    # 자동 턴 전환 활성화 여부
    AGENT_MAX_STENOGRAPHERS: int = 4        # 최대 속기사 수
    
    # 자막 관리 설정 (CaptionManager)
    AGENT_CAPTION_RETENTION_MS: int = 60000 # 자막 버퍼 보관 시간 (밀리초)
    AGENT_CAPTION_SYNC_INTERVAL_MS: int = 500  # 검수자 자막 동기화 간격 (밀리초)
    
    # 외부 연동 설정 (ExternalConnector)
    STT_SERVICE_URL: str = ""               # STT 서비스 URL (빈 문자열이면 비활성화)
    STT_SERVICE_TIMEOUT: float = 5.0        # STT 서비스 타임아웃 (초)
    OCR_SERVICE_URL: str = ""               # OCR 서비스 URL (빈 문자열이면 비활성화)
    OCR_SERVICE_TIMEOUT: float = 5.0        # OCR 서비스 타임아웃 (초)
    BROADCAST_OUTPUT_URL: str = ""          # 방송국 전송 URL (빈 문자열이면 비활성화)
    BROADCAST_OUTPUT_TIMEOUT: float = 10.0  # 방송국 전송 타임아웃 (초)
    
    # Agent Identity 설정
    AGENT_IDENTITY: str = "room-agent"      # RoomAgent identity
    
    @property
    def stt_enabled(self) -> bool:
        """STT 서비스 활성화 여부"""
        return bool(self.STT_SERVICE_URL)
    
    @property
    def ocr_enabled(self) -> bool:
        """OCR 서비스 활성화 여부"""
        return bool(self.OCR_SERVICE_URL)
    
    @property
    def broadcast_enabled(self) -> bool:
        """방송국 전송 활성화 여부"""
        return bool(self.BROADCAST_OUTPUT_URL)

    @property
    def livekit_http_url(self) -> str:
        """LiveKit HTTP API URL (ws:// -> http://)"""
        url = self.LIVEKIT_URL
        return url.replace("wss://", "https://").replace("ws://", "http://")

    @property
    def livekit_ws_url(self) -> str:
        """LiveKit WebSocket URL"""
        url = self.LIVEKIT_URL
        if url.startswith("http://"):
            return url.replace("http://", "ws://")
        elif url.startswith("https://"):
            return url.replace("https://", "wss://")
        return url

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
