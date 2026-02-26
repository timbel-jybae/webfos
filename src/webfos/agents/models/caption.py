"""
자막 데이터 모델.

속기사가 작성하는 자막 세그먼트와 관련 데이터 구조를 정의한다.
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import time


class CaptionStatus(Enum):
    """
    자막 상태
    
    - DRAFT: 작성 중 (속기사가 입력 중)
    - SUBMITTED: 제출됨 (속기사가 작성 완료)
    - MERGED: 병합됨 (다른 세그먼트와 병합 완료)
    - REVIEWED: 검수됨 (검수자가 확인/수정 완료)
    - FINAL: 최종 확정 (외부 전달 가능)
    """
    DRAFT = "draft"
    SUBMITTED = "submitted"
    MERGED = "merged"
    REVIEWED = "reviewed"
    FINAL = "final"


@dataclass
class CaptionSegment:
    """
    자막 세그먼트
    
    속기사가 작성하는 자막의 기본 단위.
    각 세그먼트는 특정 시간 구간에 대응하며, 하나의 턴 내에서 생성된다.
    
    Attributes:
        id: 세그먼트 고유 ID (UUID)
        turn_id: 소속 턴 ID
        
        timestamp_start_ms: 시작 타임스탬프 (영상 기준, 밀리초)
        timestamp_end_ms: 종료 타임스탬프 (영상 기준, 밀리초)
        
        text: 자막 텍스트
        author_identity: 작성자 속기사 identity
        
        stt_reference: STT 원본 텍스트 (참고용)
        ocr_reference: OCR 감지 텍스트 (참고용)
        
        status: 자막 상태
        
        reviewed_by: 검수자 identity (검수된 경우)
        review_note: 검수 메모
        original_text: 검수 전 원본 텍스트 (수정된 경우)
        
        created_at: 생성 시각 (서버 시간, Unix timestamp)
        updated_at: 수정 시각 (서버 시간, Unix timestamp)
    """
    turn_id: str
    timestamp_start_ms: int
    text: str
    author_identity: str
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_end_ms: Optional[int] = None
    
    stt_reference: Optional[str] = None
    ocr_reference: Optional[str] = None
    
    status: CaptionStatus = CaptionStatus.DRAFT
    
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    original_text: Optional[str] = None
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def update_text(self, new_text: str) -> "CaptionSegment":
        """
        자막 텍스트 수정 (작성 중)
        
        Args:
            new_text: 새 텍스트
            
        Returns:
            self (체이닝 지원)
        """
        if self.original_text is None and self.text:
            self.original_text = self.text
        self.text = new_text
        self.updated_at = time.time()
        return self
    
    def submit(self, timestamp_end_ms: int) -> "CaptionSegment":
        """
        자막 제출
        
        Args:
            timestamp_end_ms: 종료 타임스탬프
            
        Returns:
            self (체이닝 지원)
        """
        self.timestamp_end_ms = timestamp_end_ms
        self.status = CaptionStatus.SUBMITTED
        self.updated_at = time.time()
        return self
    
    def mark_merged(self) -> "CaptionSegment":
        """
        병합 완료 표시
        
        Returns:
            self (체이닝 지원)
        """
        self.status = CaptionStatus.MERGED
        self.updated_at = time.time()
        return self
    
    def review(
        self,
        reviewer_identity: str,
        new_text: Optional[str] = None,
        note: Optional[str] = None,
    ) -> "CaptionSegment":
        """
        자막 검수
        
        Args:
            reviewer_identity: 검수자 identity
            new_text: 수정된 텍스트 (수정 시)
            note: 검수 메모
            
        Returns:
            self (체이닝 지원)
        """
        self.reviewed_by = reviewer_identity
        self.review_note = note
        
        if new_text is not None and new_text != self.text:
            self.original_text = self.text
            self.text = new_text
        
        self.status = CaptionStatus.REVIEWED
        self.updated_at = time.time()
        return self
    
    def finalize(self) -> "CaptionSegment":
        """
        최종 확정
        
        Returns:
            self (체이닝 지원)
        """
        self.status = CaptionStatus.FINAL
        self.updated_at = time.time()
        return self
    
    def is_draft(self) -> bool:
        """작성 중 상태인지 확인"""
        return self.status == CaptionStatus.DRAFT
    
    def is_final(self) -> bool:
        """최종 확정 상태인지 확인"""
        return self.status == CaptionStatus.FINAL
    
    def is_in_range(self, timestamp_ms: int, window_ms: int = 500) -> bool:
        """
        특정 타임스탬프가 이 세그먼트 범위 내인지 확인
        
        Args:
            timestamp_ms: 확인할 타임스탬프
            window_ms: 허용 오차 (밀리초)
            
        Returns:
            범위 내 여부
        """
        start = self.timestamp_start_ms - window_ms
        end = (self.timestamp_end_ms or self.timestamp_start_ms) + window_ms
        return start <= timestamp_ms <= end
    
    def duration_ms(self) -> Optional[int]:
        """
        세그먼트 지속 시간 (밀리초)
        
        Returns:
            지속 시간, 종료되지 않았으면 None
        """
        if self.timestamp_end_ms is None:
            return None
        return self.timestamp_end_ms - self.timestamp_start_ms
    
    def to_dict(self) -> dict:
        """딕셔너리 변환 (직렬화용)"""
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "timestamp_start_ms": self.timestamp_start_ms,
            "timestamp_end_ms": self.timestamp_end_ms,
            "text": self.text,
            "author_identity": self.author_identity,
            "stt_reference": self.stt_reference,
            "ocr_reference": self.ocr_reference,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "review_note": self.review_note,
            "original_text": self.original_text,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CaptionSegment":
        """딕셔너리에서 생성 (역직렬화용)"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            turn_id=data["turn_id"],
            timestamp_start_ms=data["timestamp_start_ms"],
            timestamp_end_ms=data.get("timestamp_end_ms"),
            text=data["text"],
            author_identity=data["author_identity"],
            stt_reference=data.get("stt_reference"),
            ocr_reference=data.get("ocr_reference"),
            status=CaptionStatus(data.get("status", "draft")),
            reviewed_by=data.get("reviewed_by"),
            review_note=data.get("review_note"),
            original_text=data.get("original_text"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class STTResult:
    """
    STT 결과 데이터
    
    외부 STT 서비스로부터 수신한 음성 인식 결과.
    
    Attributes:
        text: 인식된 텍스트
        timestamp_ms: 타임스탬프 (영상 기준)
        confidence: 신뢰도 (0.0 ~ 1.0)
        is_final: 최종 결과 여부 (중간 결과 vs 확정 결과)
        received_at: 수신 시각
    """
    text: str
    timestamp_ms: int
    confidence: float = 1.0
    is_final: bool = True
    received_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        """딕셔너리 변환"""
        return {
            "text": self.text,
            "timestamp_ms": self.timestamp_ms,
            "confidence": self.confidence,
            "is_final": self.is_final,
            "received_at": self.received_at,
        }


@dataclass
class OCRResult:
    """
    OCR 결과 데이터
    
    외부 OCR 서비스로부터 수신한 텍스트 감지 결과.
    
    Attributes:
        text: 감지된 텍스트
        timestamp_ms: 타임스탬프 (영상 기준)
        region: 감지 영역 {"x": int, "y": int, "width": int, "height": int}
        confidence: 신뢰도 (0.0 ~ 1.0)
        received_at: 수신 시각
    """
    text: str
    timestamp_ms: int
    region: dict = field(default_factory=dict)
    confidence: float = 1.0
    received_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        """딕셔너리 변환"""
        return {
            "text": self.text,
            "timestamp_ms": self.timestamp_ms,
            "region": self.region,
            "confidence": self.confidence,
            "received_at": self.received_at,
        }
