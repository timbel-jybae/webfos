"""
[advice from AI] HLS 동기화 테스트용 FastAPI 백엔드

서버 기동 시 Ingress 생성, 토큰 발급 API 제공.
- lifespan: HLS Ingress 생성
- GET /api/prepare: ws_url, room, 참가자 토큰 목록 반환
- POST /api/token: identity, name으로 토큰 발급

환경변수: .env 파일 사용 (backend/.env 또는 dev/test_by_agent/.env)
"""

import os
import asyncio
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

# [advice from AI] .env 로드: backend/.env 우선, 없으면 상위 .env
_env_paths = [
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
for p in _env_paths:
    if p.exists():
        load_dotenv(p)
        break
else:
    load_dotenv()  # CWD 기준
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# 전역: Ingress 생성 후 room/ws_url 저장
_room_state = {"room_name": None, "ws_url": None, "ingress_id": None, "ingress_delayed_id": None}


def _get_livekit_api():
    """[advice from AI] LiveKit API 클라이언트 생성 헬퍼"""
    from livekit import api

    livekit_url = os.getenv("LIVEKIT_URL", "").strip()
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, api_key, api_secret]):
        raise RuntimeError("LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET 환경변수 필요")

    if livekit_url.startswith("://"):
        livekit_url = "http" + livekit_url
    elif not (livekit_url.startswith("http://") or livekit_url.startswith("https://")):
        livekit_url = "http://" + livekit_url

    return api.LiveKitAPI(livekit_url, api_key, api_secret), livekit_url


async def _cleanup_old_ingresses(room_name: str):
    """[advice from AI] 기존 Ingress 전부 삭제 — 좀비 누적 방지"""
    from livekit.protocol.ingress import ListIngressRequest, DeleteIngressRequest

    lkapi, _ = _get_livekit_api()
    try:
        resp = await lkapi.ingress.list_ingress(ListIngressRequest(room_name=room_name))
        if resp.items:
            print(f"[cleanup] {room_name}에 기존 Ingress {len(resp.items)}개 발견, 삭제 중...")
            for ing in resp.items:
                try:
                    await lkapi.ingress.delete_ingress(DeleteIngressRequest(ingress_id=ing.ingress_id))
                    print(f"[cleanup] 삭제: {ing.ingress_id} ({ing.name})")
                except Exception as e:
                    print(f"[cleanup] 삭제 실패: {ing.ingress_id} - {e}")
    finally:
        await lkapi.aclose()


async def _delete_ingress(ingress_id: str):
    """[advice from AI] 단일 Ingress 삭제"""
    from livekit.protocol.ingress import DeleteIngressRequest

    lkapi, _ = _get_livekit_api()
    try:
        await lkapi.ingress.delete_ingress(DeleteIngressRequest(ingress_id=ingress_id))
        print(f"[shutdown] Ingress 삭제: {ingress_id}")
    except Exception as e:
        print(f"[shutdown] Ingress 삭제 실패: {ingress_id} - {e}")
    finally:
        await lkapi.aclose()


async def _create_ingress():
    """[advice from AI] HLS Ingress 생성 (기존 Ingress 정리 후)"""
    from livekit.protocol.ingress import CreateIngressRequest, IngressInput

    room_name = "hls-sync-test-room"
    hls_url = os.getenv(
        "HLS_URL",
        "https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8",
    )

    # [advice from AI] 기존 Ingress 정리 — 좀비 누적 방지
    await _cleanup_old_ingresses(room_name)

    lkapi, livekit_url = _get_livekit_api()

    req_realtime = CreateIngressRequest(
        input_type=IngressInput.URL_INPUT,
        name="hls-ingress-realtime",
        room_name=room_name,
        participant_identity="ingress-hls-source",
        participant_name="HLS Source",
        url=hls_url,
    )
    info_realtime = await lkapi.ingress.create_ingress(req_realtime)
    print(f"[backend] Ingress 실시간 생성: {info_realtime.ingress_id}")

    await lkapi.aclose()

    ws_url = livekit_url.replace("https://", "wss://").replace("http://", "ws://")
    _room_state["room_name"] = room_name
    _room_state["ws_url"] = ws_url
    _room_state["ingress_id"] = info_realtime.ingress_id
    _room_state["ingress_delayed_id"] = None
    return room_name, ws_url


def _generate_token(identity: str, name: str, room_name: str) -> str:
    """참가자용 JWT 토큰 생성"""
    from livekit.api.access_token import AccessToken, VideoGrants

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("LIVEKIT_API_KEY, LIVEKIT_API_SECRET 환경변수 필요")

    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
    )
    return token.to_jwt()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """[advice from AI] 서버 기동 시 Ingress 생성, 종료 시 삭제"""
    try:
        await _create_ingress()
        print(f"[OK] Ingress 생성 완료: room={_room_state['room_name']}")
    except Exception as e:
        print(f"[WARN] Ingress 생성 실패 (API 호출 시 재시도): {e}")
    yield
    # [advice from AI] shutdown 시 Ingress 삭제 — 좀비 누적 방지
    ingress_id = _room_state.get("ingress_id")
    if ingress_id:
        try:
            await _delete_ingress(ingress_id)
        except Exception as e:
            print(f"[WARN] shutdown Ingress 삭제 실패: {e}")
    _room_state.clear()


app = FastAPI(
    title="HLS 동기화 테스트 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/prepare")
async def prepare():
    """
    Ingress/룸 준비 상태 및 참가자 토큰 반환.
    Ingress가 없으면 생성 후 반환.
    """
    room_name = _room_state.get("room_name")
    ws_url = _room_state.get("ws_url")

    if not room_name or not ws_url:
        try:
            room_name, ws_url = await _create_ingress()
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))

    participants = [
        ("participant-1", "참가자 1"),
        ("participant-2", "참가자 2"),
        ("participant-3", "참가자 3"),
        ("reviewer", "검수자"),
    ]
    tokens = [
        {"identity": i, "name": n, "token": _generate_token(i, n, room_name)}
        for i, n in participants
    ]

    return {
        "ws_url": ws_url,
        "room": room_name,
        "participants": tokens,
    }


class TokenRequest(BaseModel):
    identity: str
    name: Optional[str] = None


class AgentTokenRequest(BaseModel):
    room_name: Optional[str] = None


@app.post("/api/agent-token")
def get_agent_token(req: AgentTokenRequest):
    """[advice from AI] 지연 Agent용 토큰 발급"""
    room_name = req.room_name or _room_state.get("room_name")
    if not room_name:
        raise HTTPException(
            status_code=503,
            detail="룸이 준비되지 않았습니다. /api/prepare 를 먼저 호출하세요.",
        )
    token = _generate_token("delay-agent", "지연 스트림 (검수자용)", room_name)
    return {"token": token, "ws_url": _room_state.get("ws_url"), "room": room_name}


@app.post("/api/token")
def get_token(req: TokenRequest):
    """참가자 토큰 발급"""
    room_name = _room_state.get("room_name")
    ws_url = _room_state.get("ws_url")

    if not room_name or not ws_url:
        raise HTTPException(
            status_code=503,
            detail="Ingress가 준비되지 않았습니다. /api/prepare 를 먼저 호출하세요.",
        )

    token = _generate_token(req.identity, req.name or req.identity, room_name)
    return {"token": token, "ws_url": ws_url, "room": room_name}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "32055"))
    uvicorn.run(app, host="0.0.0.0", port=port)
