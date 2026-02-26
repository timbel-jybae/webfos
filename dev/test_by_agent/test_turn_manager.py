"""
TurnManager 단위 테스트.

테스트 실행:
    cd dev/test_by_agent
    python test_turn_manager.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "webfos"))

from agents.turn_manager import TurnManager, TurnSwitchResult
from agents.models.turn import Turn, TurnState


async def test_init():
    """TurnManager 초기화"""
    manager = TurnManager(
        turn_duration_ms=30000,
        auto_switch=False,
        max_stenographers=4,
    )
    
    assert manager.turn_duration_ms == 30000
    assert manager.auto_switch == False
    assert manager.max_stenographers == 4
    
    print("✓ test_init 통과")


async def test_register_participant():
    """참가자 등록"""
    manager = TurnManager()
    
    assert manager.register_participant("steno-1", "stenographer", "속기사1") == True
    assert manager.register_participant("steno-2", "stenographer", "속기사2") == True
    assert manager.register_participant("reviewer-1", "reviewer", "검수자1") == True
    
    assert manager.register_participant("steno-1", "stenographer") == False
    
    assert len(manager.get_stenographers()) == 2
    assert len(manager.get_reviewers()) == 1
    
    print("✓ test_register_participant 통과")


async def test_max_stenographers():
    """최대 속기사 수 제한"""
    manager = TurnManager(max_stenographers=2)
    
    assert manager.register_participant("steno-1", "stenographer") == True
    assert manager.register_participant("steno-2", "stenographer") == True
    assert manager.register_participant("steno-3", "stenographer") == False
    
    assert len(manager.get_stenographers()) == 2
    
    print("✓ test_max_stenographers 통과")


async def test_unregister_participant():
    """참가자 등록 해제"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    assert manager.unregister_participant("steno-1") == True
    assert len(manager.get_stenographers()) == 1
    
    assert manager.unregister_participant("unknown") == False
    
    print("✓ test_unregister_participant 통과")


async def test_start_turn():
    """턴 시작"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    
    turn = await manager.start_turn("steno-1", timestamp_ms=1000)
    
    assert turn is not None
    assert turn.holder_identity == "steno-1"
    assert turn.start_timestamp_ms == 1000
    assert turn.state == TurnState.ACTIVE
    assert manager.get_current_holder() == "steno-1"
    
    print("✓ test_start_turn 통과")


async def test_start_turn_invalid():
    """잘못된 턴 시작"""
    manager = TurnManager()
    
    turn = await manager.start_turn("unknown", timestamp_ms=1000)
    assert turn is None
    
    manager.register_participant("reviewer-1", "reviewer")
    turn = await manager.start_turn("reviewer-1", timestamp_ms=1000)
    assert turn is None
    
    print("✓ test_start_turn_invalid 통과")


async def test_end_turn():
    """턴 종료"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    await manager.start_turn("steno-1", timestamp_ms=1000)
    
    turn = await manager.end_turn(timestamp_ms=5000)
    
    assert turn is not None
    assert turn.state == TurnState.COMPLETED
    assert turn.duration_ms() == 4000
    assert manager.get_current_holder() is None
    
    history = manager.get_turn_history()
    assert len(history) == 1
    
    print("✓ test_end_turn 통과")


async def test_switch_turn():
    """턴 전환"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    result = await manager.switch_turn("steno-2", timestamp_ms=5000)
    
    assert result.success == True
    assert result.previous_turn is not None
    assert result.previous_turn.holder_identity == "steno-1"
    assert result.new_turn is not None
    assert result.new_turn.holder_identity == "steno-2"
    assert manager.get_current_holder() == "steno-2"
    
    print("✓ test_switch_turn 통과")


async def test_switch_turn_auto_select():
    """턴 전환 - 자동 선택"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    result = await manager.switch_turn(None, timestamp_ms=5000)
    
    assert result.success == True
    assert result.new_turn.holder_identity == "steno-2"
    
    print("✓ test_switch_turn_auto_select 통과")


async def test_request_turn_switch():
    """턴 전환 요청"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    success = await manager.request_turn_switch("steno-1", timestamp_ms=5000)
    assert success == True
    assert manager.get_current_holder() == "steno-2"
    
    print("✓ test_request_turn_switch 통과")


async def test_request_turn_switch_not_holder():
    """턴 전환 요청 - 권한 없음"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    success = await manager.request_turn_switch("steno-2", timestamp_ms=5000)
    assert success == False
    assert manager.get_current_holder() == "steno-1"
    
    print("✓ test_request_turn_switch_not_holder 통과")


async def test_has_permission():
    """권한 확인"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("steno-2", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    assert manager.has_permission("steno-1") == True
    assert manager.has_permission("steno-2") == False
    assert manager.has_permission("unknown") == False
    
    print("✓ test_has_permission 통과")


async def test_add_segment_to_turn():
    """턴에 세그먼트 추가"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    turn = await manager.start_turn("steno-1", timestamp_ms=0)
    
    assert manager.add_segment_to_current_turn("seg-1") == True
    assert manager.add_segment_to_current_turn("seg-2") == True
    
    assert "seg-1" in turn.segment_ids
    assert "seg-2" in turn.segment_ids
    
    print("✓ test_add_segment_to_turn 통과")


async def test_turn_callbacks():
    """턴 콜백"""
    manager = TurnManager()
    
    started_turns = []
    ended_turns = []
    
    async def on_start(turn):
        started_turns.append(turn)
    
    async def on_end(turn):
        ended_turns.append(turn)
    
    manager.on_turn_start(on_start)
    manager.on_turn_end(on_end)
    
    manager.register_participant("steno-1", "stenographer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    assert len(started_turns) == 1
    
    await manager.end_turn(timestamp_ms=5000)
    assert len(ended_turns) == 1
    
    print("✓ test_turn_callbacks 통과")


async def test_get_stats():
    """통계 정보"""
    manager = TurnManager(turn_duration_ms=30000, auto_switch=True)
    
    manager.register_participant("steno-1", "stenographer")
    manager.register_participant("reviewer-1", "reviewer")
    
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    stats = manager.get_stats()
    
    assert stats["total_turns"] == 1
    assert stats["current_holder"] == "steno-1"
    assert stats["stenographer_count"] == 1
    assert stats["reviewer_count"] == 1
    assert stats["auto_switch"] == True
    assert stats["turn_duration_ms"] == 30000
    
    manager._cancel_auto_switch_timer()
    
    print("✓ test_get_stats 통과")


async def test_stop():
    """TurnManager 중지"""
    manager = TurnManager()
    
    manager.register_participant("steno-1", "stenographer")
    await manager.start_turn("steno-1", timestamp_ms=0)
    
    await manager.stop()
    
    assert manager.get_current_turn() is None
    assert len(manager.get_stenographers()) == 0
    
    print("✓ test_stop 통과")


async def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 50)
    print("TurnManager 단위 테스트")
    print("=" * 50)
    
    tests = [
        test_init,
        test_register_participant,
        test_max_stenographers,
        test_unregister_participant,
        test_start_turn,
        test_start_turn_invalid,
        test_end_turn,
        test_switch_turn,
        test_switch_turn_auto_select,
        test_request_turn_switch,
        test_request_turn_switch_not_holder,
        test_has_permission,
        test_add_segment_to_turn,
        test_turn_callbacks,
        test_get_stats,
        test_stop,
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
