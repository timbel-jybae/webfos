"""
VideoRouter 단위 테스트.

테스트 실행:
    cd dev/test_by_agent
    python test_video_router.py
    
참고: LiveKit 모듈 없이 기본 기능만 테스트합니다.
실제 트랙 처리는 통합 테스트에서 수행합니다.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "webfos"))

from agents.video_router import VideoRouter, FrameRingBuffer


class MockFrame:
    """테스트용 모의 프레임"""
    def __init__(self, data: str):
        self.data = data


async def test_video_router_init():
    """VideoRouter 초기화"""
    router = VideoRouter(
        delay_ms=3500,
        buffer_margin_ms=1000,
        fps=30,
    )
    
    assert router.delay_ms == 3500
    assert router.buffer_margin_ms == 1000
    assert router.fps == 30
    assert router.video_buffer.max_duration_ms == 4500
    assert router.audio_buffer.max_duration_ms == 4500
    assert not router._is_running
    
    print("✓ test_video_router_init 통과")


async def test_video_router_default_values():
    """VideoRouter 기본값"""
    router = VideoRouter()
    
    assert router.delay_ms == 3500
    assert router.buffer_margin_ms == 1000
    assert router.fps == 30
    
    print("✓ test_video_router_default_values 통과")


async def test_timestamp_calculation():
    """타임스탬프 계산"""
    router = VideoRouter(delay_ms=3500)
    
    router._base_timestamp_ms = 0
    router._current_timestamp_ms = 5000
    
    current = router.get_current_timestamp()
    assert current == 5000
    
    delayed = router.get_delayed_timestamp()
    assert delayed == 1500
    
    print("✓ test_timestamp_calculation 통과")


async def test_delayed_timestamp_zero_clamp():
    """지연 타임스탬프 0 이하 방지"""
    router = VideoRouter(delay_ms=3500)
    
    router._current_timestamp_ms = 1000
    
    delayed = router.get_delayed_timestamp()
    assert delayed == 0, f"음수 타임스탬프 발생: {delayed}"
    
    print("✓ test_delayed_timestamp_zero_clamp 통과")


async def test_stats():
    """통계 정보"""
    router = VideoRouter(delay_ms=3500)
    
    router._current_timestamp_ms = 5000
    
    stats = router.get_stats()
    
    assert stats["is_running"] == False
    assert stats["delay_ms"] == 3500
    assert stats["current_timestamp_ms"] == 5000
    assert stats["delayed_timestamp_ms"] == 1500
    assert "video_buffer" in stats
    assert "audio_buffer" in stats
    
    print("✓ test_stats 통과")


async def test_buffer_independence():
    """비디오/오디오 버퍼 독립성"""
    router = VideoRouter(delay_ms=3500)
    
    await router.video_buffer.push(MockFrame("video1"), timestamp_ms=1000)
    await router.video_buffer.push(MockFrame("video2"), timestamp_ms=2000)
    
    await router.audio_buffer.push(MockFrame("audio1"), timestamp_ms=1500)
    
    video_size = await router.video_buffer.size()
    audio_size = await router.audio_buffer.size()
    
    assert video_size == 2
    assert audio_size == 1
    
    print("✓ test_buffer_independence 통과")


async def test_stop_without_start():
    """시작하지 않은 상태에서 중지"""
    router = VideoRouter()
    
    await router.stop()
    
    assert not router._is_running
    
    print("✓ test_stop_without_start 통과")


async def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 50)
    print("VideoRouter 단위 테스트 (모의 환경)")
    print("=" * 50)
    
    tests = [
        test_video_router_init,
        test_video_router_default_values,
        test_timestamp_calculation,
        test_delayed_timestamp_zero_clamp,
        test_stats,
        test_buffer_independence,
        test_stop_without_start,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} 실패: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} 오류: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"결과: {passed} 통과, {failed} 실패")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
