"""
턴 관리 모듈.

속기사들의 작업 턴을 관리하여 자막 작업 충돌을 방지한다.
- 턴 할당 및 전환
- 작업 권한 제어
- 턴 상태 브로드캐스트
"""

import asyncio
from typing import Optional, List, Dict, Callable, Awaitable
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from .models.turn import Turn, TurnState, Participant


@dataclass
class TurnSwitchResult:
    """턴 전환 결과"""
    success: bool
    previous_turn: Optional[Turn] = None
    new_turn: Optional[Turn] = None
    message: str = ""


class TurnManager:
    """
    속기사 턴 관리
    
    속기사들의 작업 턴을 관리하여 동시 작업 충돌을 방지한다.
    한 번에 한 명의 속기사만 작업 권한을 가진다.
    
    Attributes:
        turn_duration_ms: 기본 턴 지속 시간 (자동 전환 시)
        auto_switch: 자동 턴 전환 활성화 여부
        max_stenographers: 최대 속기사 수
    
    Example:
        manager = TurnManager(turn_duration_ms=30000)
        manager.register_participant("steno-1", "stenographer")
        manager.register_participant("steno-2", "stenographer")
        
        turn = await manager.start_turn("steno-1", timestamp_ms=0)
        ...
        result = await manager.switch_turn("steno-2", timestamp_ms=30000)
    """
    
    def __init__(
        self,
        turn_duration_ms: int = 30000,
        auto_switch: bool = False,
        max_stenographers: int = 4,
    ):
        """
        Args:
            turn_duration_ms: 기본 턴 지속 시간 (밀리초)
            auto_switch: 자동 턴 전환 활성화 여부
            max_stenographers: 최대 속기사 수
        """
        self.turn_duration_ms = turn_duration_ms
        self.auto_switch = auto_switch
        self.max_stenographers = max_stenographers
        
        self._participants: Dict[str, Participant] = {}
        self._stenographer_queue: deque[str] = deque()
        
        self._current_turn: Optional[Turn] = None
        self._turn_history: List[Turn] = []
        self._turn_count = 0
        
        self._auto_switch_task: Optional[asyncio.Task] = None
        
        self._on_turn_start_callbacks: List[Callable[[Turn], Awaitable[None]]] = []
        self._on_turn_end_callbacks: List[Callable[[Turn], Awaitable[None]]] = []
        
        logger.info(
            f"[TurnManager] 초기화: duration={turn_duration_ms}ms, "
            f"auto_switch={auto_switch}"
        )
    
    def register_participant(self, identity: str, role: str, name: str = "") -> bool:
        """
        참가자 등록
        
        Args:
            identity: 참가자 고유 ID
            role: "stenographer" | "reviewer"
            name: 표시 이름
            
        Returns:
            등록 성공 여부
        """
        if identity in self._participants:
            logger.warning(f"[TurnManager] 이미 등록된 참가자: {identity}")
            return False
        
        if role == "stenographer":
            stenographer_count = sum(
                1 for p in self._participants.values() if p.is_stenographer()
            )
            if stenographer_count >= self.max_stenographers:
                logger.warning(
                    f"[TurnManager] 최대 속기사 수 초과: {self.max_stenographers}"
                )
                return False
        
        participant = Participant(
            identity=identity,
            role=role,
            name=name or identity,
        )
        self._participants[identity] = participant
        
        if role == "stenographer":
            self._stenographer_queue.append(identity)
        
        logger.info(f"[TurnManager] 참가자 등록: {identity} ({role})")
        return True
    
    def unregister_participant(self, identity: str) -> bool:
        """
        참가자 등록 해제
        
        Args:
            identity: 참가자 ID
            
        Returns:
            해제 성공 여부
        """
        if identity not in self._participants:
            return False
        
        participant = self._participants.pop(identity)
        
        if participant.is_stenographer():
            if identity in self._stenographer_queue:
                self._stenographer_queue.remove(identity)
        
        logger.info(f"[TurnManager] 참가자 해제: {identity}")
        return True
    
    def get_participant(self, identity: str) -> Optional[Participant]:
        """참가자 조회"""
        return self._participants.get(identity)
    
    def get_stenographers(self) -> List[Participant]:
        """속기사 목록"""
        return [p for p in self._participants.values() if p.is_stenographer()]
    
    def get_reviewers(self) -> List[Participant]:
        """검수자 목록"""
        return [p for p in self._participants.values() if p.is_reviewer()]
    
    async def start_turn(self, holder_identity: str, timestamp_ms: int) -> Optional[Turn]:
        """
        새 턴 시작
        
        Args:
            holder_identity: 턴 권한 부여할 속기사
            timestamp_ms: 시작 영상 타임스탬프
            
        Returns:
            생성된 Turn 객체, 실패 시 None
        """
        if holder_identity not in self._participants:
            logger.error(f"[TurnManager] 등록되지 않은 참가자: {holder_identity}")
            return None
        
        participant = self._participants[holder_identity]
        if not participant.is_stenographer():
            logger.error(f"[TurnManager] 속기사가 아님: {holder_identity}")
            return None
        
        if self._current_turn and self._current_turn.is_active():
            logger.warning("[TurnManager] 활성 턴이 있음, 먼저 종료 필요")
            return None
        
        self._turn_count += 1
        turn = Turn(
            holder_identity=holder_identity,
            start_timestamp_ms=timestamp_ms,
            id=f"turn-{self._turn_count}",
        )
        turn.start()
        
        self._current_turn = turn
        
        if holder_identity in self._stenographer_queue:
            self._stenographer_queue.remove(holder_identity)
        self._stenographer_queue.append(holder_identity)
        
        logger.info(
            f"[TurnManager] 턴 시작: {turn.id}, holder={holder_identity}, "
            f"timestamp={timestamp_ms}ms"
        )
        
        for callback in self._on_turn_start_callbacks:
            try:
                await callback(turn)
            except Exception as e:
                logger.error(f"[TurnManager] 턴 시작 콜백 오류: {e}")
        
        if self.auto_switch:
            self._start_auto_switch_timer(timestamp_ms)
        
        return turn
    
    async def end_turn(self, timestamp_ms: int) -> Optional[Turn]:
        """
        현재 턴 종료
        
        Args:
            timestamp_ms: 종료 영상 타임스탬프
            
        Returns:
            종료된 Turn 객체, 실패 시 None
        """
        if not self._current_turn:
            logger.warning("[TurnManager] 종료할 턴 없음")
            return None
        
        self._cancel_auto_switch_timer()
        
        turn = self._current_turn
        turn.end(timestamp_ms)
        
        self._turn_history.append(turn)
        self._current_turn = None
        
        logger.info(
            f"[TurnManager] 턴 종료: {turn.id}, "
            f"duration={turn.duration_ms()}ms"
        )
        
        for callback in self._on_turn_end_callbacks:
            try:
                await callback(turn)
            except Exception as e:
                logger.error(f"[TurnManager] 턴 종료 콜백 오류: {e}")
        
        return turn
    
    async def switch_turn(
        self,
        next_holder: Optional[str],
        timestamp_ms: int,
    ) -> TurnSwitchResult:
        """
        턴 전환 (종료 + 시작 원자적 수행)
        
        Args:
            next_holder: 다음 턴 권한자 (None이면 대기열에서 선택)
            timestamp_ms: 전환 시점 타임스탬프
            
        Returns:
            TurnSwitchResult
        """
        previous_turn = await self.end_turn(timestamp_ms)
        
        if next_holder is None:
            next_holder = self._get_next_stenographer()
        
        if next_holder is None:
            return TurnSwitchResult(
                success=False,
                previous_turn=previous_turn,
                message="다음 속기사 없음",
            )
        
        new_turn = await self.start_turn(next_holder, timestamp_ms)
        
        if new_turn is None:
            return TurnSwitchResult(
                success=False,
                previous_turn=previous_turn,
                message="새 턴 시작 실패",
            )
        
        return TurnSwitchResult(
            success=True,
            previous_turn=previous_turn,
            new_turn=new_turn,
            message="턴 전환 완료",
        )
    
    async def request_turn_switch(self, requester_identity: str, timestamp_ms: int) -> bool:
        """
        턴 전환 요청 (속기사가 작업 완료 시 호출)
        
        현재 턴 보유자만 전환 요청 가능.
        
        Args:
            requester_identity: 요청자 ID
            timestamp_ms: 요청 시점 타임스탬프
            
        Returns:
            요청 수락 여부
        """
        if not self._current_turn:
            logger.warning("[TurnManager] 활성 턴 없음")
            return False
        
        if self._current_turn.holder_identity != requester_identity:
            logger.warning(
                f"[TurnManager] 턴 보유자가 아님: {requester_identity} "
                f"(현재: {self._current_turn.holder_identity})"
            )
            return False
        
        next_holder = self._get_next_stenographer(exclude=requester_identity)
        result = await self.switch_turn(next_holder, timestamp_ms)
        
        return result.success
    
    def _get_next_stenographer(self, exclude: Optional[str] = None) -> Optional[str]:
        """
        다음 속기사 선택 (라운드 로빈)
        
        [advice from AI] 리스트 기반 순환:
        - 현재 보유자의 다음 인덱스 반환
        - 마지막 인덱스면 0으로 순환
        - 1명이면 자기 자신 반환
        
        Args:
            exclude: 현재 턴 보유자 (다음 사람 찾기 기준점)
            
        Returns:
            다음 속기사 identity
        """
        active_stenos = [
            identity for identity in self._stenographer_queue
            if self._participants.get(identity) and self._participants[identity].is_active
        ]
        
        if not active_stenos:
            return None
        
        if len(active_stenos) == 1:
            return active_stenos[0]
        
        if exclude and exclude in active_stenos:
            current_idx = active_stenos.index(exclude)
            next_idx = (current_idx + 1) % len(active_stenos)
            return active_stenos[next_idx]
        
        return active_stenos[0]
    
    def has_permission(self, identity: str) -> bool:
        """
        작업 권한 확인
        
        Args:
            identity: 확인할 참가자 ID
            
        Returns:
            권한 보유 여부
        """
        if not self._current_turn:
            return False
        return self._current_turn.holder_identity == identity
    
    def get_current_holder(self) -> Optional[str]:
        """현재 턴 권한자 반환"""
        if self._current_turn:
            return self._current_turn.holder_identity
        return None
    
    def get_current_turn(self) -> Optional[Turn]:
        """현재 턴 반환"""
        return self._current_turn
    
    def get_turn_queue(self) -> List[str]:
        """턴 대기열 반환"""
        return list(self._stenographer_queue)
    
    def get_turn_history(self, limit: int = 10) -> List[Turn]:
        """턴 기록 반환"""
        return self._turn_history[-limit:]
    
    def add_segment_to_current_turn(self, segment_id: str) -> bool:
        """
        현재 턴에 자막 세그먼트 ID 추가
        
        Args:
            segment_id: 세그먼트 ID
            
        Returns:
            추가 성공 여부
        """
        if not self._current_turn:
            return False
        self._current_turn.add_segment(segment_id)
        return True
    
    def on_turn_start(self, callback: Callable[[Turn], Awaitable[None]]) -> None:
        """턴 시작 콜백 등록"""
        self._on_turn_start_callbacks.append(callback)
    
    def on_turn_end(self, callback: Callable[[Turn], Awaitable[None]]) -> None:
        """턴 종료 콜백 등록"""
        self._on_turn_end_callbacks.append(callback)
    
    def _start_auto_switch_timer(self, start_timestamp_ms: int) -> None:
        """자동 전환 타이머 시작"""
        self._cancel_auto_switch_timer()
        
        async def auto_switch():
            await asyncio.sleep(self.turn_duration_ms / 1000.0)
            if self._current_turn:
                end_ts = start_timestamp_ms + self.turn_duration_ms
                logger.info(f"[TurnManager] 자동 턴 전환: timestamp={end_ts}ms")
                await self.switch_turn(None, end_ts)
        
        self._auto_switch_task = asyncio.create_task(auto_switch())
    
    def _cancel_auto_switch_timer(self) -> None:
        """자동 전환 타이머 취소"""
        if self._auto_switch_task:
            self._auto_switch_task.cancel()
            self._auto_switch_task = None
    
    async def stop(self) -> None:
        """TurnManager 중지 및 리소스 정리"""
        logger.info("[TurnManager] 중지")
        
        self._cancel_auto_switch_timer()
        
        if self._current_turn:
            await self.end_turn(0)
        
        self._participants.clear()
        self._stenographer_queue.clear()
        self._on_turn_start_callbacks.clear()
        self._on_turn_end_callbacks.clear()
    
    def get_stats(self) -> dict:
        """TurnManager 통계"""
        return {
            "total_turns": self._turn_count,
            "current_turn": self._current_turn.to_dict() if self._current_turn else None,
            "current_holder": self.get_current_holder(),
            "stenographer_count": len(self.get_stenographers()),
            "reviewer_count": len(self.get_reviewers()),
            "queue": self.get_turn_queue(),
            "auto_switch": self.auto_switch,
            "turn_duration_ms": self.turn_duration_ms,
        }
