"""
FrameRingBuffer 단위 테스트.

테스트 실행:
    cd src/webfos
    python -m pytest ../../dev/test_by_agent/test_frame_ring_buffer.py -v
    
또는:
    cd dev/test_by_agent
    python test_frame_ring_buffer.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "webfos"))

from agents.video_router import FrameRingBuffer, BufferedFrame


class MockFrame:
    """테스트용 모의 프레임"""
    def __init__(self, data: str):
        self.data = data
    
    def __repr__(self):
        return f"MockFrame({self.data})"


async def test_push_and_size():
    """프레임 추가 및 크기 확인"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    assert await buffer.size() == 0
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    assert await buffer.size() == 1
    
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    assert await buffer.size() == 2
    
    await buffer.push(MockFrame("frame3"), timestamp_ms=3000)
    assert await buffer.size() == 3
    
    print("✓ test_push_and_size 통과")


async def test_auto_cleanup():
    """오래된 프레임 자동 정리 (LRU)"""
    buffer = FrameRingBuffer(max_duration_ms=2000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    await buffer.push(MockFrame("frame3"), timestamp_ms=3000)
    
    await buffer.push(MockFrame("frame4"), timestamp_ms=4000)
    
    size = await buffer.size()
    assert size <= 3, f"오래된 프레임이 정리되지 않음: size={size}"
    
    oldest = await buffer.peek_oldest()
    assert oldest is not None
    assert oldest.timestamp_ms >= 2000, f"오래된 프레임 남음: {oldest.timestamp_ms}"
    
    print("✓ test_auto_cleanup 통과")


async def test_read_delayed():
    """지연된 프레임 읽기"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    await buffer.push(MockFrame("frame3"), timestamp_ms=3000)
    await buffer.push(MockFrame("frame4"), timestamp_ms=4000)
    
    delayed = await buffer.read_delayed(delay_ms=2000)
    
    assert delayed is not None
    assert delayed.timestamp_ms == 2000, f"잘못된 타임스탬프: {delayed.timestamp_ms}"
    assert delayed.frame.data == "frame2"
    
    size_after = await buffer.size()
    assert size_after == 4, "read_delayed는 프레임을 제거하지 않아야 함"
    
    print("✓ test_read_delayed 통과")


async def test_read_delayed_and_remove():
    """지연된 프레임 읽기 및 이전 프레임 제거"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    await buffer.push(MockFrame("frame3"), timestamp_ms=3000)
    await buffer.push(MockFrame("frame4"), timestamp_ms=4000)
    
    delayed = await buffer.read_delayed_and_remove(delay_ms=2000)
    
    assert delayed is not None
    assert delayed.timestamp_ms == 2000
    
    size_after = await buffer.size()
    assert size_after < 4, "read_delayed_and_remove는 이전 프레임을 제거해야 함"
    
    oldest = await buffer.peek_oldest()
    assert oldest is not None
    assert oldest.timestamp_ms >= 2000, "2000ms 이전 프레임이 제거되지 않음"
    
    print("✓ test_read_delayed_and_remove 통과")


async def test_empty_buffer():
    """빈 버퍼 처리"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    delayed = await buffer.read_delayed(delay_ms=2000)
    assert delayed is None
    
    oldest = await buffer.peek_oldest()
    assert oldest is None
    
    newest = await buffer.peek_newest()
    assert newest is None
    
    duration = await buffer.get_buffer_duration_ms()
    assert duration == 0
    
    print("✓ test_empty_buffer 통과")


async def test_buffer_duration():
    """버퍼 시간 범위 계산"""
    buffer = FrameRingBuffer(max_duration_ms=10000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2500)
    await buffer.push(MockFrame("frame3"), timestamp_ms=4000)
    
    duration = await buffer.get_buffer_duration_ms()
    assert duration == 3000, f"잘못된 duration: {duration}"
    
    print("✓ test_buffer_duration 통과")


async def test_clear():
    """버퍼 초기화"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    
    await buffer.clear()
    
    assert await buffer.size() == 0
    
    print("✓ test_clear 통과")


async def test_stats():
    """통계 정보"""
    buffer = FrameRingBuffer(max_duration_ms=2000)
    
    await buffer.push(MockFrame("frame1"), timestamp_ms=1000)
    await buffer.push(MockFrame("frame2"), timestamp_ms=2000)
    await buffer.push(MockFrame("frame3"), timestamp_ms=3000)
    await buffer.push(MockFrame("frame4"), timestamp_ms=4000)
    
    stats = buffer.get_stats()
    
    assert stats["frame_count"] == 4
    assert stats["dropped_count"] > 0
    assert stats["max_duration_ms"] == 2000
    
    print("✓ test_stats 통과")


async def test_concurrent_access():
    """동시성 테스트"""
    buffer = FrameRingBuffer(max_duration_ms=5000)
    
    async def push_frames():
        for i in range(100):
            await buffer.push(MockFrame(f"frame{i}"), timestamp_ms=i * 10)
            await asyncio.sleep(0.001)
    
    async def read_frames():
        for _ in range(50):
            await buffer.read_delayed(delay_ms=100)
            await asyncio.sleep(0.002)
    
    await asyncio.gather(
        push_frames(),
        read_frames(),
        read_frames(),
    )
    
    size = await buffer.size()
    assert size > 0, "동시 접근 후 버퍼가 비어있음"
    
    print("✓ test_concurrent_access 통과")


async def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 50)
    print("FrameRingBuffer 단위 테스트")
    print("=" * 50)
    
    tests = [
        test_push_and_size,
        test_auto_cleanup,
        test_read_delayed,
        test_read_delayed_and_remove,
        test_empty_buffer,
        test_buffer_duration,
        test_clear,
        test_stats,
        test_concurrent_access,
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
