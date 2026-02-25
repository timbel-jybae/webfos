"""
프로젝트 설정 — Pydantic Settings 기반.

환경변수 자동 로드, 타입 검증, 기본값 제공.
모든 레이어에서 `from core.config import settings`로 참조한다.

[사용법]
- .env 파일 또는 환경변수로 값을 주입
- @property로 파생 값 정의
- @lru_cache()로 싱글톤 보장
"""

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache
import os


class Settings(BaseSettings):

    # === 기본 설정 ===
    PROJECT_NAME: str = "MyService"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    DEBUG: bool = False

    # === 서버 설정 ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False
    WORKERS: int = 1

    # === DB 설정 ===
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = ""
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_SCHEMA: str = "public"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # === Celery 설정 (선택적) ===
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND_URL: str = "redis://localhost:6379/2"

    # === 외부 서비스 설정 (예시) ===
    # LIVEKIT_API_URL: str = ""
    # LIVEKIT_API_KEY: str = ""
    # LIVEKIT_API_SECRET: str = ""
    # LIVEKIT_TIMEOUT: float = 10.0

    # === 경로 설정 ===
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # === 로깅 ===
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
