"""
자막 관리 모듈.

속기사가 작성한 자막 세그먼트를 수집, 저장, 병합, 조회한다.
- 타임스탬프 기반 저장/조회
- 버퍼 관리 (retention_ms 기반 정리)
- 턴 단위 자막 병합
"""

import asyncio
from typing import Optional, List, Dict, Callable, Awaitable, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import time

from loguru import logger

from .models.caption import CaptionSegment, CaptionStatus, STTResult, OCRResult


CaptionCallback = Callable[[CaptionSegment], Awaitable[None]]


@dataclass
class MergedCaption:
    """병합된 자막 결과"""
    turn_id: str
    timestamp_start_ms: int
    timestamp_end_ms: int
    text: str
    segment_ids: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "timestamp_start_ms": self.timestamp_start_ms,
            "timestamp_end_ms": self.timestamp_end_ms,
            "text": self.text,
            "segment_ids": self.segment_ids,
            "created_at": self.created_at,
        }


class CaptionManager:
    """
    자막 관리자
    
    속기사가 작성한 자막 세그먼트를 관리하고 병합한다.
    
    Attributes:
        retention_ms: 자막 버퍼 보관 시간 (밀리초)
    
    Example:
        manager = CaptionManager(retention_ms=60000)
        
        segment = manager.create_segment(
            turn_id="turn-1",
            timestamp_start_ms=1000,
            text="안녕하세요",
            author_identity="steno-1",
        )
        manager.submit_segment(segment.id)
        
        captions = manager.get_segments_in_range(0, 5000)
    """
    
    def __init__(self, retention_ms: int = 60000):
        """
        Args:
            retention_ms: 자막 버퍼 보관 시간 (밀리초)
        """
        self.retention_ms = retention_ms
        
        self._segments: Dict[str, CaptionSegment] = {}
        self._segments_by_turn: Dict[str, List[str]] = defaultdict(list)
        self._segments_by_timestamp: Dict[int, List[str]] = defaultdict(list)
        
        self._merged_captions: Dict[str, MergedCaption] = {}
        
        self._stt_results: List[STTResult] = []
        self._ocr_results: List[OCRResult] = []
        
        self._on_segment_created: List[CaptionCallback] = []
        self._on_segment_submitted: List[CaptionCallback] = []
        self._on_segment_merged: List[CaptionCallback] = []
        
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        logger.info(f"[CaptionManager] 초기화: retention={retention_ms}ms")
    
    async def start(self) -> None:
        """CaptionManager 시작 (주기적 정리 태스크 시작)"""
        if self._cleanup_task:
            return
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[CaptionManager] 시작")
    
    async def stop(self) -> None:
        """CaptionManager 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        self._segments.clear()
        self._segments_by_turn.clear()
        self._segments_by_timestamp.clear()
        self._merged_captions.clear()
        self._stt_results.clear()
        self._ocr_results.clear()
        
        logger.info("[CaptionManager] 중지")
    
    async def _cleanup_loop(self) -> None:
        """주기적 버퍼 정리"""
        cleanup_interval = max(self.retention_ms / 4, 5000) / 1000.0
        
        while True:
            try:
                await asyncio.sleep(cleanup_interval)
                await self._cleanup_old_segments()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CaptionManager] 정리 오류: {e}")
    
    async def _cleanup_old_segments(self) -> None:
        """오래된 세그먼트 정리"""
        async with self._lock:
            current_time = time.time()
            cutoff_time = current_time - (self.retention_ms / 1000.0)
            
            to_remove = []
            for seg_id, segment in self._segments.items():
                if segment.created_at < cutoff_time and segment.is_final():
                    to_remove.append(seg_id)
            
            for seg_id in to_remove:
                self._remove_segment(seg_id)
            
            if to_remove:
                logger.debug(f"[CaptionManager] {len(to_remove)}개 세그먼트 정리")
    
    def _remove_segment(self, segment_id: str) -> None:
        """세그먼트 제거 (내부용)"""
        if segment_id not in self._segments:
            return
        
        segment = self._segments.pop(segment_id)
        
        if segment.turn_id in self._segments_by_turn:
            try:
                self._segments_by_turn[segment.turn_id].remove(segment_id)
            except ValueError:
                pass
        
        ts_key = segment.timestamp_start_ms // 1000
        if ts_key in self._segments_by_timestamp:
            try:
                self._segments_by_timestamp[ts_key].remove(segment_id)
            except ValueError:
                pass
    
    def create_segment(
        self,
        turn_id: str,
        timestamp_start_ms: int,
        text: str,
        author_identity: str,
        timestamp_end_ms: Optional[int] = None,
        stt_reference: Optional[str] = None,
        ocr_reference: Optional[str] = None,
    ) -> CaptionSegment:
        """
        새 자막 세그먼트 생성
        
        Args:
            turn_id: 턴 ID
            timestamp_start_ms: 시작 타임스탬프 (밀리초)
            text: 자막 텍스트
            author_identity: 작성자 identity
            timestamp_end_ms: 종료 타임스탬프 (옵션)
            stt_reference: STT 참조 텍스트
            ocr_reference: OCR 참조 텍스트
            
        Returns:
            생성된 CaptionSegment
        """
        segment = CaptionSegment(
            turn_id=turn_id,
            timestamp_start_ms=timestamp_start_ms,
            text=text,
            author_identity=author_identity,
            timestamp_end_ms=timestamp_end_ms,
            stt_reference=stt_reference,
            ocr_reference=ocr_reference,
        )
        
        self._segments[segment.id] = segment
        self._segments_by_turn[turn_id].append(segment.id)
        
        ts_key = timestamp_start_ms // 1000
        self._segments_by_timestamp[ts_key].append(segment.id)
        
        logger.debug(
            f"[CaptionManager] 세그먼트 생성: {segment.id}, "
            f"turn={turn_id}, ts={timestamp_start_ms}ms"
        )
        
        asyncio.create_task(self._fire_callbacks(self._on_segment_created, segment))
        
        return segment
    
    def get_segment(self, segment_id: str) -> Optional[CaptionSegment]:
        """세그먼트 조회"""
        return self._segments.get(segment_id)
    
    def update_segment(
        self,
        segment_id: str,
        text: str,
        timestamp_end_ms: Optional[int] = None,
    ) -> Optional[CaptionSegment]:
        """
        세그먼트 업데이트
        
        Args:
            segment_id: 세그먼트 ID
            text: 새 텍스트
            timestamp_end_ms: 종료 타임스탬프 (옵션)
            
        Returns:
            업데이트된 CaptionSegment, 실패 시 None
        """
        segment = self._segments.get(segment_id)
        if not segment:
            logger.warning(f"[CaptionManager] 세그먼트 없음: {segment_id}")
            return None
        
        if not segment.is_draft():
            logger.warning(f"[CaptionManager] 수정 불가 상태: {segment.status}")
            return None
        
        segment.update_text(text)
        if timestamp_end_ms is not None:
            segment.timestamp_end_ms = timestamp_end_ms
        
        return segment
    
    def submit_segment(
        self,
        segment_id: str,
        timestamp_end_ms: Optional[int] = None,
    ) -> bool:
        """
        세그먼트 제출
        
        Args:
            segment_id: 세그먼트 ID
            timestamp_end_ms: 종료 타임스탬프 (없으면 시작 타임스탬프 사용)
            
        Returns:
            성공 여부
        """
        segment = self._segments.get(segment_id)
        if not segment:
            return False
        
        end_ts = timestamp_end_ms or segment.timestamp_end_ms or segment.timestamp_start_ms
        segment.submit(end_ts)
        
        logger.debug(f"[CaptionManager] 세그먼트 제출: {segment_id}")
        
        asyncio.create_task(self._fire_callbacks(self._on_segment_submitted, segment))
        
        return True
    
    def get_segments_by_turn(self, turn_id: str) -> List[CaptionSegment]:
        """턴별 세그먼트 조회"""
        segment_ids = self._segments_by_turn.get(turn_id, [])
        segments = [
            self._segments[sid]
            for sid in segment_ids
            if sid in self._segments
        ]
        return sorted(segments, key=lambda s: s.timestamp_start_ms)
    
    def get_segments_in_range(
        self,
        start_ms: int,
        end_ms: int,
        status: Optional[CaptionStatus] = None,
    ) -> List[CaptionSegment]:
        """
        시간 범위 내 세그먼트 조회
        
        Args:
            start_ms: 시작 타임스탬프
            end_ms: 종료 타임스탬프
            status: 필터링할 상태 (옵션)
            
        Returns:
            범위 내 CaptionSegment 리스트
        """
        result = []
        
        start_key = start_ms // 1000
        end_key = end_ms // 1000 + 1
        
        for ts_key in range(start_key, end_key + 1):
            segment_ids = self._segments_by_timestamp.get(ts_key, [])
            for seg_id in segment_ids:
                segment = self._segments.get(seg_id)
                if segment and segment.is_in_range(start_ms, end_ms):
                    if status is None or segment.status == status:
                        result.append(segment)
        
        return sorted(result, key=lambda s: s.timestamp_start_ms)
    
    def get_submitted_segments(self, turn_id: Optional[str] = None) -> List[CaptionSegment]:
        """제출된 세그먼트 조회"""
        if turn_id:
            segments = self.get_segments_by_turn(turn_id)
        else:
            segments = list(self._segments.values())
        
        return [
            s for s in segments
            if s.status in (CaptionStatus.SUBMITTED, CaptionStatus.MERGED)
        ]
    
    def merge_segments(self, turn_id: str) -> Optional[MergedCaption]:
        """
        턴 내 세그먼트 병합
        
        제출된 세그먼트들을 타임스탬프 순으로 정렬하여 병합한다.
        
        Args:
            turn_id: 턴 ID
            
        Returns:
            병합된 MergedCaption, 병합 대상 없으면 None
        """
        segments = self.get_segments_by_turn(turn_id)
        submitted = [s for s in segments if s.status == CaptionStatus.SUBMITTED]
        
        if not submitted:
            logger.debug(f"[CaptionManager] 병합 대상 없음: {turn_id}")
            return None
        
        submitted.sort(key=lambda s: s.timestamp_start_ms)
        
        merged_text_parts = []
        segment_ids = []
        
        for segment in submitted:
            segment.mark_merged()
            merged_text_parts.append(segment.text)
            segment_ids.append(segment.id)
            
            asyncio.create_task(
                self._fire_callbacks(self._on_segment_merged, segment)
            )
        
        merged_text = " ".join(merged_text_parts)
        
        merged = MergedCaption(
            turn_id=turn_id,
            timestamp_start_ms=submitted[0].timestamp_start_ms,
            timestamp_end_ms=submitted[-1].timestamp_end_ms or submitted[-1].timestamp_start_ms,
            text=merged_text,
            segment_ids=segment_ids,
        )
        
        self._merged_captions[turn_id] = merged
        
        logger.info(
            f"[CaptionManager] 세그먼트 병합: turn={turn_id}, "
            f"segments={len(submitted)}, text_length={len(merged_text)}"
        )
        
        return merged
    
    def get_merged_caption(self, turn_id: str) -> Optional[MergedCaption]:
        """병합된 자막 조회"""
        return self._merged_captions.get(turn_id)
    
    def add_stt_result(self, result: STTResult) -> None:
        """STT 결과 추가"""
        self._stt_results.append(result)
        
        if len(self._stt_results) > 100:
            self._stt_results = self._stt_results[-50:]
        
        logger.debug(f"[CaptionManager] STT 결과 추가: ts={result.timestamp_ms}ms")
    
    def add_ocr_result(self, result: OCRResult) -> None:
        """OCR 결과 추가"""
        self._ocr_results.append(result)
        
        if len(self._ocr_results) > 100:
            self._ocr_results = self._ocr_results[-50:]
        
        logger.debug(f"[CaptionManager] OCR 결과 추가: ts={result.timestamp_ms}ms")
    
    def get_recent_stt(self, since_ms: int) -> List[STTResult]:
        """최근 STT 결과 조회"""
        return [r for r in self._stt_results if r.timestamp_ms >= since_ms]
    
    def get_recent_ocr(self, since_ms: int) -> List[OCRResult]:
        """최근 OCR 결과 조회"""
        return [r for r in self._ocr_results if r.timestamp_ms >= since_ms]
    
    def review_segment(
        self,
        segment_id: str,
        reviewed_by: str,
        new_text: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[CaptionSegment]:
        """
        세그먼트 검수
        
        Args:
            segment_id: 세그먼트 ID
            reviewed_by: 검수자 identity
            new_text: 수정된 텍스트 (옵션)
            note: 검수 메모 (옵션)
            
        Returns:
            검수된 CaptionSegment
        """
        segment = self._segments.get(segment_id)
        if not segment:
            return None
        
        segment.review(reviewed_by, new_text, note)
        
        logger.info(f"[CaptionManager] 세그먼트 검수: {segment_id} by {reviewed_by}")
        
        return segment
    
    def finalize_segment(self, segment_id: str) -> Optional[CaptionSegment]:
        """세그먼트 최종 확정"""
        segment = self._segments.get(segment_id)
        if not segment:
            return None
        
        segment.finalize()
        
        logger.info(f"[CaptionManager] 세그먼트 확정: {segment_id}")
        
        return segment
    
    def on_segment_created(self, callback: CaptionCallback) -> None:
        """세그먼트 생성 콜백 등록"""
        self._on_segment_created.append(callback)
    
    def on_segment_submitted(self, callback: CaptionCallback) -> None:
        """세그먼트 제출 콜백 등록"""
        self._on_segment_submitted.append(callback)
    
    def on_segment_merged(self, callback: CaptionCallback) -> None:
        """세그먼트 병합 콜백 등록"""
        self._on_segment_merged.append(callback)
    
    async def _fire_callbacks(
        self,
        callbacks: List[CaptionCallback],
        segment: CaptionSegment,
    ) -> None:
        """콜백 실행"""
        for callback in callbacks:
            try:
                await callback(segment)
            except Exception as e:
                logger.error(f"[CaptionManager] 콜백 오류: {e}")
    
    def get_stats(self) -> dict:
        """통계 정보"""
        status_counts = defaultdict(int)
        for segment in self._segments.values():
            status_counts[segment.status.value] += 1
        
        return {
            "total_segments": len(self._segments),
            "merged_captions": len(self._merged_captions),
            "stt_results": len(self._stt_results),
            "ocr_results": len(self._ocr_results),
            "status_counts": dict(status_counts),
            "retention_ms": self.retention_ms,
        }
