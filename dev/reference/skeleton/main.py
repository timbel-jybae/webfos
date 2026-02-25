"""
FastAPI 엔트리포인트 — Lifespan 기반 생명주기 관리.

[Lifespan 시작 시]
1. DB 초기화 (스키마/테이블 생성)
2. 모델/리소스 로드
3. 웜업 (첫 요청 지연 제거)
4. 백그라운드 태스크 시작

[Lifespan 종료 시]
1. 스케줄러 중지
2. 클라이언트 리소스 정리
"""

import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger

from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서비스 시작/종료 시 실행"""

    # === 시작 ===
    logger.info(f"{settings.PROJECT_NAME} v{settings.VERSION} 시작")

    # 1. DB 초기화
    # from db.database import init_db
    # init_db()

    # 2. 서비스 리소스 로드
    # from services.domain_service import domain_service
    # domain_service.load_resources()

    # 3. 백그라운드 태스크
    # from managers.scheduler import scheduler
    # scheduler.start()

    logger.info("서비스 준비 완료")

    yield

    # === 종료 ===
    # from managers.scheduler import scheduler
    # scheduler.stop()

    # from clients.example_client import example_client
    # await example_client.close()

    logger.info("서비스 종료")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# 라우터 등록
# from api.endpoints.domain_endpoints import router as domain_router
# app.include_router(domain_router, prefix=f"{settings.API_V1_STR}/domain", tags=["Domain"])


@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS,
    )
