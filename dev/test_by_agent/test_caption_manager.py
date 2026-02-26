"""
CaptionManager 단위 테스트.

테스트 실행:
    cd dev/test_by_agent
    python test_caption_manager.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "webfos"))

from agents.caption_manager import CaptionManager, MergedCaption
from agents.models.caption import CaptionSegment, CaptionStatus, STTResult, OCRResult


async def test_init():
    """CaptionManager 초기화"""
    manager = CaptionManager(retention_ms=60000)
    
    assert manager.retention_ms == 60000
    
    stats = manager.get_stats()
    assert stats["total_segments"] == 0
    assert stats["merged_captions"] == 0
    
    print("✓ test_init 통과")


async def test_create_segment():
    """세그먼트 생성"""
    manager = CaptionManager()
    
    segment = manager.create_segment(
        turn_id="turn-1",
        timestamp_start_ms=1000,
        text="안녕하세요",
        author_identity="steno-1",
    )
    
    assert segment is not None
    assert segment.turn_id == "turn-1"
    assert segment.timestamp_start_ms == 1000
    assert segment.text == "안녕하세요"
    assert segment.author_identity == "steno-1"
    assert segment.status == CaptionStatus.DRAFT
    
    assert manager.get_segment(segment.id) == segment
    
    print("✓ test_create_segment 통과")


async def test_update_segment():
    """세그먼트 업데이트"""
    manager = CaptionManager()
    
    segment = manager.create_segment(
        turn_id="turn-1",
        timestamp_start_ms=1000,
        text="안녕",
        author_identity="steno-1",
    )
    
    updated = manager.update_segment(
        segment.id,
        text="안녕하세요",
        timestamp_end_ms=2000,
    )
    
    assert updated is not None
    assert updated.text == "안녕하세요"
    assert updated.timestamp_end_ms == 2000
    assert updated.original_text == "안녕"
    
    print("✓ test_update_segment 통과")


async def test_submit_segment():
    """세그먼트 제출"""
    manager = CaptionManager()
    
    segment = manager.create_segment(
        turn_id="turn-1",
        timestamp_start_ms=1000,
        text="안녕하세요",
        author_identity="steno-1",
    )
    
    success = manager.submit_segment(segment.id)
    
    assert success == True
    assert segment.status == CaptionStatus.SUBMITTED
    
    update_result = manager.update_segment(segment.id, text="수정")
    assert update_result is None
    
    print("✓ test_submit_segment 통과")


async def test_get_segments_by_turn():
    """턴별 세그먼트 조회"""
    manager = CaptionManager()
    
    manager.create_segment("turn-1", 1000, "첫번째", "steno-1")
    manager.create_segment("turn-1", 2000, "두번째", "steno-1")
    manager.create_segment("turn-2", 3000, "세번째", "steno-2")
    
    turn1_segments = manager.get_segments_by_turn("turn-1")
    assert len(turn1_segments) == 2
    assert turn1_segments[0].timestamp_start_ms == 1000
    assert turn1_segments[1].timestamp_start_ms == 2000
    
    turn2_segments = manager.get_segments_by_turn("turn-2")
    assert len(turn2_segments) == 1
    
    print("✓ test_get_segments_by_turn 통과")


async def test_get_segments_in_range():
    """시간 범위 내 세그먼트 조회"""
    manager = CaptionManager()
    
    manager.create_segment("turn-1", 1000, "A", "steno-1")
    manager.create_segment("turn-1", 3000, "B", "steno-1")
    manager.create_segment("turn-1", 5000, "C", "steno-1")
    
    segments = manager.get_segments_in_range(0, 4000)
    assert len(segments) == 2
    
    segments = manager.get_segments_in_range(2000, 6000)
    assert len(segments) == 2
    
    segments = manager.get_segments_in_range(10000, 20000)
    assert len(segments) == 0
    
    print("✓ test_get_segments_in_range 통과")


async def test_merge_segments():
    """세그먼트 병합"""
    manager = CaptionManager()
    
    seg1 = manager.create_segment("turn-1", 1000, "안녕", "steno-1")
    seg2 = manager.create_segment("turn-1", 2000, "하세요", "steno-1")
    seg3 = manager.create_segment("turn-1", 3000, "반갑습니다", "steno-1")
    
    manager.submit_segment(seg1.id)
    manager.submit_segment(seg2.id)
    manager.submit_segment(seg3.id)
    
    merged = manager.merge_segments("turn-1")
    
    assert merged is not None
    assert merged.turn_id == "turn-1"
    assert merged.text == "안녕 하세요 반갑습니다"
    assert len(merged.segment_ids) == 3
    assert merged.timestamp_start_ms == 1000
    assert merged.timestamp_end_ms == 3000
    
    assert seg1.status == CaptionStatus.MERGED
    assert seg2.status == CaptionStatus.MERGED
    assert seg3.status == CaptionStatus.MERGED
    
    print("✓ test_merge_segments 통과")


async def test_merge_segments_partial():
    """일부 제출된 세그먼트만 병합"""
    manager = CaptionManager()
    
    seg1 = manager.create_segment("turn-1", 1000, "A", "steno-1")
    seg2 = manager.create_segment("turn-1", 2000, "B", "steno-1")
    seg3 = manager.create_segment("turn-1", 3000, "C", "steno-1")
    
    manager.submit_segment(seg1.id)
    manager.submit_segment(seg2.id)
    
    merged = manager.merge_segments("turn-1")
    
    assert merged.text == "A B"
    assert len(merged.segment_ids) == 2
    assert seg3.status == CaptionStatus.DRAFT
    
    print("✓ test_merge_segments_partial 통과")


async def test_merge_segments_empty():
    """병합 대상 없음"""
    manager = CaptionManager()
    
    manager.create_segment("turn-1", 1000, "A", "steno-1")
    
    merged = manager.merge_segments("turn-1")
    assert merged is None
    
    merged = manager.merge_segments("turn-nonexistent")
    assert merged is None
    
    print("✓ test_merge_segments_empty 통과")


async def test_review_segment():
    """세그먼트 검수"""
    manager = CaptionManager()
    
    segment = manager.create_segment("turn-1", 1000, "안녕", "steno-1")
    manager.submit_segment(segment.id)
    
    reviewed = manager.review_segment(
        segment.id,
        reviewed_by="reviewer-1",
        new_text="안녕하세요",
        note="인사말 수정",
    )
    
    assert reviewed is not None
    assert reviewed.status == CaptionStatus.REVIEWED
    assert reviewed.text == "안녕하세요"
    assert reviewed.reviewed_by == "reviewer-1"
    assert reviewed.review_note == "인사말 수정"
    
    print("✓ test_review_segment 통과")


async def test_finalize_segment():
    """세그먼트 최종 확정"""
    manager = CaptionManager()
    
    segment = manager.create_segment("turn-1", 1000, "안녕", "steno-1")
    manager.submit_segment(segment.id)
    manager.review_segment(segment.id, "reviewer-1")
    
    finalized = manager.finalize_segment(segment.id)
    
    assert finalized is not None
    assert finalized.status == CaptionStatus.FINAL
    
    print("✓ test_finalize_segment 통과")


async def test_stt_ocr_results():
    """STT/OCR 결과 관리"""
    manager = CaptionManager()
    
    stt1 = STTResult(text="테스트", timestamp_ms=1000)
    stt2 = STTResult(text="텍스트", timestamp_ms=2000)
    
    manager.add_stt_result(stt1)
    manager.add_stt_result(stt2)
    
    recent = manager.get_recent_stt(1500)
    assert len(recent) == 1
    assert recent[0].text == "텍스트"
    
    ocr1 = OCRResult(text="OCR1", timestamp_ms=1000)
    manager.add_ocr_result(ocr1)
    
    ocr_recent = manager.get_recent_ocr(0)
    assert len(ocr_recent) == 1
    
    print("✓ test_stt_ocr_results 통과")


async def test_callbacks():
    """콜백 테스트"""
    manager = CaptionManager()
    
    created_segments = []
    submitted_segments = []
    merged_segments = []
    
    async def on_created(segment):
        created_segments.append(segment)
    
    async def on_submitted(segment):
        submitted_segments.append(segment)
    
    async def on_merged(segment):
        merged_segments.append(segment)
    
    manager.on_segment_created(on_created)
    manager.on_segment_submitted(on_submitted)
    manager.on_segment_merged(on_merged)
    
    segment = manager.create_segment("turn-1", 1000, "테스트", "steno-1")
    await asyncio.sleep(0.01)
    assert len(created_segments) == 1
    
    manager.submit_segment(segment.id)
    await asyncio.sleep(0.01)
    assert len(submitted_segments) == 1
    
    manager.merge_segments("turn-1")
    await asyncio.sleep(0.01)
    assert len(merged_segments) == 1
    
    print("✓ test_callbacks 통과")


async def test_get_stats():
    """통계 정보"""
    manager = CaptionManager()
    
    seg1 = manager.create_segment("turn-1", 1000, "A", "steno-1")
    seg2 = manager.create_segment("turn-1", 2000, "B", "steno-1")
    manager.submit_segment(seg1.id)
    
    stats = manager.get_stats()
    
    assert stats["total_segments"] == 2
    assert stats["status_counts"]["draft"] == 1
    assert stats["status_counts"]["submitted"] == 1
    
    print("✓ test_get_stats 통과")


async def test_start_stop():
    """시작/중지"""
    manager = CaptionManager(retention_ms=1000)
    
    await manager.start()
    
    manager.create_segment("turn-1", 1000, "A", "steno-1")
    
    await manager.stop()
    
    assert manager.get_stats()["total_segments"] == 0
    
    print("✓ test_start_stop 통과")


async def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 50)
    print("CaptionManager 단위 테스트")
    print("=" * 50)
    
    tests = [
        test_init,
        test_create_segment,
        test_update_segment,
        test_submit_segment,
        test_get_segments_by_turn,
        test_get_segments_in_range,
        test_merge_segments,
        test_merge_segments_partial,
        test_merge_segments_empty,
        test_review_segment,
        test_finalize_segment,
        test_stt_ocr_results,
        test_callbacks,
        test_get_stats,
        test_start_stop,
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
