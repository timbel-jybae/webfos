"""
Webfos FastAPI 엔트리포인트 — Lifespan 기반 생명주기 관리.

[Lifespan 시작 시]
1. 채널별 Ingress 생성
2. 각 Room에 Agent dispatch (livekit-agents Worker가 별도 프로세스로 처리)

[Lifespan 종료 시]
1. Ingress 삭제 (좀비 방지)
2. LiveKit 클라이언트 정리
3. 룸 상태 정리

[advice from AI] RoomAgent는 livekit-agents 프레임워크 기반으로 분리.
Agent Worker는 별도 프로세스(agents/room_agent_worker.py)로 실행하며,
Ingress 생성 시 자동으로 Agent가 Room에 dispatch된다.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서비스 시작/종료 시 실행"""

    # === 시작 ===
    logger.info(f"{settings.PROJECT_NAME} v{settings.VERSION} 시작")
    logger.info(f"LiveKit URL: {settings.LIVEKIT_URL}")
    
    from managers.channel_manager import channel_manager
    from clients.redis_client import redis_client
    
    # [advice from AI] Redis 연결 및 초기화
    try:
        if await redis_client.connect():
            deleted = await redis_client.cleanup_all()
            logger.info(f"Redis 초기화 완료: {deleted}개 키 삭제")
        else:
            logger.warning("Redis 연결 실패 - 상태 공유 비활성화")
    except Exception as e:
        logger.warning(f"Redis 초기화 실패: {e}")
    
    # 채널 Ingress 병렬 초기화 + Agent dispatch
    try:
        await channel_manager.initialize_all_ingresses(batch_size=5)
    except Exception as e:
        logger.error(f"Ingress 초기화 실패: {e}")

    logger.info("서비스 준비 완료")

    yield

    # === 종료 ===
    from clients.livekit_client import livekit_client
    from managers.room_manager import room_manager
    
    # 1. Ingress 삭제 (좀비 누적 방지)
    try:
        await channel_manager.cleanup_all_ingresses()
    except Exception as e:
        logger.error(f"Ingress 정리 실패: {e}")

    # 2. LiveKit 클라이언트 및 로컬 상태 정리
    await livekit_client.close()
    room_manager.clear()
    
    # 3. [advice from AI] Redis 연결 종료
    await redis_client.close()

    logger.info("서비스 종료")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
from api.endpoints.health_endpoints import router as health_router
from api.endpoints.room_endpoints import router as room_router
from api.endpoints.channel_endpoints import router as channel_router
from api.endpoints.admin_endpoints import router as admin_router

app.include_router(health_router, prefix="/api", tags=["Health"])
app.include_router(room_router, prefix="/api", tags=["Room"])
app.include_router(channel_router, prefix="/api", tags=["Channel"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])


@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS,
    )
