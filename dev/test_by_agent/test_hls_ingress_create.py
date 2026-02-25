#!/usr/bin/env python3
"""
[advice from AI] HLS URL → LiveKit Ingress 생성 스크립트

개발초안 Phase 2 검증용: HLS URL을 Ingress로 등록하여 지정된 Room에 스트리밍합니다.
사용법:
  python test_hls_ingress_create.py --hls-url <HLS_URL> --room <ROOM_NAME>
  환경변수: .env 파일 또는 LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

의존성: pip install livekit-api python-dotenv
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# [advice from AI] .env 로드 (dev/test_by_agent/.env 또는 backend/.env)
try:
    from dotenv import load_dotenv
    _base = Path(__file__).resolve().parent
    for _p in (_base / ".env", _base / "backend" / ".env"):
        if _p.exists():
            load_dotenv(_p)
            break
    else:
        load_dotenv()
except ImportError:
    pass


def parse_args():
    parser = argparse.ArgumentParser(description="HLS URL로 LiveKit Ingress 생성")
    parser.add_argument(
        "--hls-url",
        default="https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8",
        help="HLS 스트림 URL (기본: WOW TV 라이브)",
    )
    parser.add_argument(
        "--room",
        default="hls-sync-test-room",
        help="대상 Room 이름 (기본: hls-sync-test-room)",
    )
    parser.add_argument(
        "--participant-identity",
        default="ingress-hls-source",
        help="Ingress 참가자 Identity (기본: ingress-hls-source)",
    )
    parser.add_argument(
        "--participant-name",
        default="HLS Source",
        help="Ingress 참가자 표시 이름 (기본: HLS Source)",
    )
    parser.add_argument(
        "--ingress-name",
        default="hls-ingress-test",
        help="Ingress 이름 (기본: hls-ingress-test)",
    )
    return parser.parse_args()


async def create_hls_ingress(
    hls_url: str,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    ingress_name: str,
) -> str:
    """
    HLS URL로 LiveKit Ingress 생성.
    Returns: ingress_id
    """
    try:
        from livekit import api
        from livekit.protocol.ingress import CreateIngressRequest, IngressInput
    except ImportError as e:
        print("오류: livekit-api 패키지가 필요합니다.", file=sys.stderr)
        print("  pip install livekit-api", file=sys.stderr)
        raise SystemExit(1) from e

    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, api_key, api_secret]):
        print("오류: 환경변수 LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET 필요", file=sys.stderr)
        raise SystemExit(1)

    lkapi = api.LiveKitAPI(livekit_url, api_key, api_secret)

    # [advice from AI] URL_INPUT(2): HLS/HTTP 미디어 풀 입력
    request = CreateIngressRequest(
        input_type=IngressInput.URL_INPUT,
        name=ingress_name,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name=participant_name,
        url=hls_url,
    )

    info = await lkapi.ingress.create_ingress(request)
    await lkapi.aclose()

    return info.ingress_id


def main():
    args = parse_args()

    ingress_id = asyncio.run(
        create_hls_ingress(
            hls_url=args.hls_url,
            room_name=args.room,
            participant_identity=args.participant_identity,
            participant_name=args.participant_name,
            ingress_name=args.ingress_name,
        )
    )

    print(f"Ingress 생성 완료: {ingress_id}")
    print(f"Room: {args.room}")
    print("이제 토큰을 발급하고 참가자 페이지로 접속하세요.")


if __name__ == "__main__":
    main()
