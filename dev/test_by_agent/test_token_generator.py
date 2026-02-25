#!/usr/bin/env python3
"""
[advice from AI] LiveKit Room 참가용 JWT 토큰 발급 스크립트

참가자가 Room에 접속할 때 사용할 토큰을 생성합니다.
사용법:
  python test_token_generator.py --room <ROOM_NAME> --identity <IDENTITY> --name <NAME>
  환경변수: .env 파일 또는 LIVEKIT_API_KEY, LIVEKIT_API_SECRET

의존성: pip install livekit-api python-dotenv
"""

import argparse
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
    parser = argparse.ArgumentParser(description="LiveKit Room 참가용 토큰 발급")
    parser.add_argument(
        "--room",
        default="hls-sync-test-room",
        help="Room 이름 (기본: hls-sync-test-room)",
    )
    parser.add_argument(
        "--identity",
        required=True,
        help="참가자 Identity (예: participant-1)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="참가자 표시 이름 (기본: identity와 동일)",
    )
    parser.add_argument(
        "--output-url",
        action="store_true",
        help="LiveKit WebSocket URL도 함께 출력 (클라이언트 연결용)",
    )
    return parser.parse_args()


def generate_token(room_name: str, identity: str, name: str) -> str:
    """
    Room 참가용 JWT 토큰 생성.
    """
    try:
        from livekit.api.access_token import AccessToken, VideoGrants
    except ImportError as e:
        print("오류: livekit-api 패키지가 필요합니다.", file=sys.stderr)
        print("  pip install livekit-api", file=sys.stderr)
        raise SystemExit(1) from e

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        print("오류: 환경변수 LIVEKIT_API_KEY, LIVEKIT_API_SECRET 필요", file=sys.stderr)
        raise SystemExit(1)

    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
    )

    return token.to_jwt()


def main():
    args = parse_args()

    token = generate_token(
        room_name=args.room,
        identity=args.identity,
        name=args.name or args.identity,
    )

    print(f"TOKEN: {token}")

    if args.output_url:
        livekit_url = os.getenv("LIVEKIT_URL", "")
        # API URL이 https:// 이면 wss:// 로 변환
        ws_url = livekit_url.replace("https://", "wss://").replace("http://", "ws://")
        print(f"WS_URL: {ws_url}")


if __name__ == "__main__":
    main()
