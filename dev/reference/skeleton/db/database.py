"""
DB 엔진/세션 관리 — SQLAlchemy 기반.

- get_engine(): 엔진 싱글톤 (지연 초기화)
- get_db_context(): 세션 컨텍스트 매니저 (with문으로 사용)
- init_db(): 스키마 + 테이블 자동 생성 (lifespan에서 호출)

[확장 시]
- init_db() 안에서 새 모델을 import하면 테이블이 자동 생성된다.
- NOTIFY 트리거 등 DB 레벨 초기화도 여기서 수행한다.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from contextlib import contextmanager
from typing import Generator
from loguru import logger

from core.config import settings

Base = declarative_base()

_engine = None
_SessionLocal = None


def get_engine():
    """SQLAlchemy 엔진 싱글톤 — 지연 초기화"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=3,
            max_overflow=5,
            pool_pre_ping=True,
        )
        logger.info(f"[Database] 엔진 생성: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    return _engine


def get_session_local():
    """SessionLocal 팩토리 싱글톤"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """DB 세션 컨텍스트 매니저 — with문으로 사용"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    스키마 + 테이블 자동 생성.
    서버 시작 시 lifespan에서 호출한다.

    [새 모델 추가 시] 아래에 import문을 추가하면 테이블이 자동 생성된다.
    """
    # from db.models.example_model import ExampleModel  # 모델 임포트로 테이블 등록

    engine = get_engine()

    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.DB_SCHEMA}"))
        conn.commit()

    Base.metadata.create_all(bind=engine)
    logger.info(f"[Database] 테이블 생성 완료 (schema: {settings.DB_SCHEMA})")
