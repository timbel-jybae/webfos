"""
헬스체크 엔드포인트.

서비스 상태 확인용 API.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """서비스 헬스체크"""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """서비스 준비 상태 확인"""
    return {"status": "ready"}
