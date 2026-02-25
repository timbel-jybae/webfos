"""
[advice from AI] HLS 지연 프록시 - 서버 측 3.5초 버퍼

소스 HLS를 fetch → 세그먼트 버퍼(3.5초) → 지연된 HLS URL 제공
LiveKit 지연 Ingress가 이 URL을 소스로 사용.

환경변수:
- HLS_SOURCE_URL: 소스 HLS URL (기본: backend와 동일)
- DELAY_SEC: 지연 시간 초 (기본: 3.5)
- PORT: 서버 포트 (기본: 9999)
"""

import asyncio
import os
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlparse, quote, unquote

import aiohttp
from aiohttp import web
import m3u8

HLS_SOURCE = os.getenv("HLS_SOURCE_URL", "https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8")
DELAY_SEC = float(os.getenv("DELAY_SEC", "3.5"))
PORT = int(os.getenv("PORT", "9999"))
# [advice from AI] Docker 컨테이너에서 접근 가능한 base URL (플레이리스트 세그먼트 URL용)
# 예: http://172.17.0.1:9999 (Docker 브릿지), http://host.docker.internal:9999 (macOS/Windows)
EXTERNAL_BASE_URL = os.getenv("EXTERNAL_BASE_URL", "")

# 세그먼트 버퍼: uri -> (data, ready_at, duration, seq) - [advice from AI] 라이브 HLS는 플레이리스트가 갱신되므로 버퍼 기준으로 서빙
_segment_buffer: OrderedDict = OrderedDict()
_segment_seq = 0  # 세그먼트마다 증가하는 시퀀스 번호
_buffer_lock = asyncio.Lock()
_last_status_log = 0.0
_source_base = ""
# [advice from AI] 라이브 HLS: 플레이리스트에 최근 N개 세그먼트만 포함
PLAYLIST_SEGMENT_COUNT = 6
# [advice from AI] 미디어 플레이리스트 URL 캐시 (마스터 플레이리스트가 동적으로 바뀌는 경우 대응)
_media_playlist_url = ""


def _abs_url(base: str, path: str) -> str:
    if path.startswith("http"):
        return path
    return urljoin(base, path)


async def _fetch(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url) as r:
        r.raise_for_status()
        return await r.read()


async def _load_playlist(session: aiohttp.ClientSession, url: str) -> m3u8.M3U8:
    data = await _fetch(session, url)
    return m3u8.loads(data.decode(), uri=url)


def _is_master(pl: m3u8.M3U8) -> bool:
    return bool(pl.playlists)


async def _buffer_worker():
    """백그라운드: 소스에서 세그먼트 fetch 후 버퍼에 저장"""
    global _source_base, _last_status_log, _segment_seq, _media_playlist_url
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # [advice from AI] 미디어 플레이리스트 URL을 한 번만 resolve (마스터 URL이 동적으로 바뀌는 CDN 대응)
                if not _media_playlist_url:
                    pl = await _load_playlist(session, HLS_SOURCE)
                    if _is_master(pl):
                        first = pl.playlists[0]
                        _media_playlist_url = _abs_url(pl.base_uri or HLS_SOURCE, first.uri)
                        _source_base = _media_playlist_url.rsplit("/", 1)[0] + "/"
                        print(f"[hls-delay-proxy] media playlist resolved: {_media_playlist_url}")
                    else:
                        _media_playlist_url = HLS_SOURCE
                        _source_base = HLS_SOURCE.rsplit("/", 1)[0] + "/"
                
                # 캐시된 미디어 플레이리스트 URL 사용
                pl = await _load_playlist(session, _media_playlist_url)

                if not pl.segments:
                    await asyncio.sleep(1)
                    continue

                now = time.time()
                added = 0
                async with _buffer_lock:
                    for seg in pl.segments:
                        uri = _abs_url(pl.base_uri or _source_base or HLS_SOURCE, seg.uri)
                        if uri in _segment_buffer:
                            continue
                        try:
                            data = await _fetch(session, uri)
                            ready_at = now + DELAY_SEC
                            dur = getattr(seg, "duration", None) or 4.0
                            # [advice from AI] 세그먼트마다 고유 시퀀스 번호 부여
                            _segment_buffer[uri] = (data, ready_at, dur, _segment_seq)
                            _segment_seq += 1
                            added += 1
                            while len(_segment_buffer) > 60:
                                _segment_buffer.popitem(last=False)
                        except Exception as ex:
                            print(f"[hls-delay-proxy] segment fetch fail: {uri[:80]}... {ex}")
                    ready_cnt = sum(1 for _, (_, r, _, _) in _segment_buffer.items() if r <= now)
                    if added:
                        print(f"[hls-delay-proxy] +{added} segments, buffer={len(_segment_buffer)}, ready={ready_cnt}")
                    elif len(_segment_buffer) > 0 and time.time() - _last_status_log > 5:
                        _last_status_log = time.time()
                        print(f"[hls-delay-proxy] buffer={len(_segment_buffer)}, ready={ready_cnt} (playlist 동일)")

            except Exception as e:
                print(f"[hls-delay-proxy] buffer fetch error: {e}")
            await asyncio.sleep(0.5)


async def _serve_playlist(request: web.Request) -> web.Response:
    """[advice from AI] 버퍼에 저장된 ready 세그먼트 기준으로 플레이리스트 서빙 (라이브 HLS: 최근 N개만 포함)"""
    try:
        # [advice from AI] EXTERNAL_BASE_URL이 설정되면 사용 (Docker 컨테이너 접근용)
        if EXTERNAL_BASE_URL:
            base = EXTERNAL_BASE_URL.rstrip("/") + "/"
        else:
            base = f"{request.url.scheme}://{request.url.host}"
            if request.url.port:
                base += f":{request.url.port}"
            base += "/"
        lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:17", "#EXT-X-VERSION:3"]

        async with _buffer_lock:
            now = time.time()
            # [advice from AI] ready된 세그먼트만 필터링 후 최근 N개만 포함
            ready_segments = []
            for uri, (data, ready_at, dur, seq) in _segment_buffer.items():
                if ready_at <= now:
                    ready_segments.append((uri, dur, seq))
            
            # [advice from AI] 최근 PLAYLIST_SEGMENT_COUNT개만 포함 (라이브 HLS 슬라이딩 윈도우)
            recent_segments = ready_segments[-PLAYLIST_SEGMENT_COUNT:] if ready_segments else []
            
            if recent_segments:
                # [advice from AI] #EXT-X-MEDIA-SEQUENCE는 첫 번째 세그먼트의 시퀀스 번호
                first_seq = recent_segments[0][2]
                lines.insert(2, f"#EXT-X-MEDIA-SEQUENCE:{first_seq}")
                
                for uri, dur, seq in recent_segments:
                    lines.append(f"#EXTINF:{dur},")
                    lines.append(base + "seg?u=" + quote(uri, safe=""))

        ready_count = len(recent_segments)
        print(f"[hls-delay-proxy] playlist served: buffer={len(_segment_buffer)}, ready_segments={ready_count}")
        body = "\n".join(lines) + "\n"
        return web.Response(text=body, content_type="application/vnd.apple.mpegurl")
    except Exception as e:
        print(f"[hls-delay-proxy] playlist error: {e}")
        return web.Response(text=f"#EXTM3U\n# Error: {e}", status=502)


async def _serve_segment(request: web.Request) -> web.Response:
    """버퍼에서 세그먼트 서빙 (ready_at 이후만)"""
    uri = unquote(request.query.get("u", ""))
    if not uri:
        return web.Response(status=400)
    # [advice from AI] 세그먼트 파일명만 로깅
    seg_name = uri.rsplit("/", 1)[-1] if "/" in uri else uri[:40]
    async with _buffer_lock:
        if uri not in _segment_buffer:
            print(f"[hls-delay-proxy] seg 404: {seg_name} (buffer={len(_segment_buffer)})")
            return web.Response(status=404)
        data, ready_at, _, _ = _segment_buffer[uri]
        if time.time() < ready_at:
            print(f"[hls-delay-proxy] seg 425 TooEarly: {seg_name}")
            return web.Response(status=425)  # Too Early
    print(f"[hls-delay-proxy] seg 200: {seg_name} ({len(data)} bytes)")
    return web.Response(body=data, content_type="video/MP2T")


async def _serve_status(request: web.Request) -> web.Response:
    """[advice from AI] 버퍼 상태 확인 - Ingress 생성 전 충분한 버퍼 확인용"""
    import json
    now = time.time()
    async with _buffer_lock:
        total = len(_segment_buffer)
        ready = sum(1 for _, (_, r, _, _) in _segment_buffer.items() if r <= now)
    # [advice from AI] 최소 10개 이상 ready 상태여야 Ingress가 안정적으로 동작
    is_ready = ready >= 10
    return web.Response(
        text=json.dumps({"buffer": total, "ready": ready, "is_ready": is_ready}),
        content_type="application/json"
    )


async def start_background_tasks(app: web.Application):
    app["buffer_task"] = asyncio.create_task(_buffer_worker())
    yield
    app["buffer_task"].cancel()
    try:
        await app["buffer_task"]
    except asyncio.CancelledError:
        pass


def main():
    app = web.Application()
    app.router.add_get("/playlist.m3u8", _serve_playlist)
    app.router.add_get("/seg", _serve_segment)
    app.router.add_get("/status", _serve_status)
    app.router.add_get("/", lambda r: web.Response(status=302, headers={"Location": "/playlist.m3u8"}))
    app.cleanup_ctx.append(start_background_tasks)
    print(f"[hls-delay-proxy] DELAY={DELAY_SEC}s, SOURCE={HLS_SOURCE}, PORT={PORT}")
    if EXTERNAL_BASE_URL:
        print(f"[hls-delay-proxy] EXTERNAL_BASE_URL={EXTERNAL_BASE_URL}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
