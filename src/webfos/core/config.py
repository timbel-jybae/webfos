"""
Webfos 프로젝트 설정 — Pydantic Settings 기반.

환경변수 자동 로드, 타입 검증, 기본값 제공.
모든 레이어에서 `from core.config import settings`로 참조한다.
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
