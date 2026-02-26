"""
Room 내 메시지 프로토콜 모델.

RoomAgent와 참가자들 간의 DataChannel 통신 메시지 구조를 정의한다.
"""

from enum import Enum
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field
import time
import json


class MessageType(Enum):
    """
    메시지 타입
    
    Room 내에서 주고받는 메시지 유형을 정의한다.
    """
    
    # === 턴 관련 ===
    TURN_START = "turn.start"           # 턴 시작 알림 (Agent → All)
    TURN_END = "turn.end"               # 턴 종료 알림 (Agent → All)
    TURN_REQUEST = "turn.request"       # 턴 전환 요청 (Stenographer → Agent)
    TURN_GRANT = "turn.grant"           # 권한 부여 확인 (Agent → Stenographer)
    TURN_DENY = "turn.deny"             # 권한 거부 (Agent → Stenographer)
    TURN_STATUS = "turn.status"         # 턴 상태 조회 응답 (Agent → Requester)
    
    # === 자막 관련 ===
    CAPTION_DRAFT = "caption.draft"     # 작성 중 자막 (Stenographer → Agent)
    CAPTION_SUBMIT = "caption.submit"   # 자막 제출 (Stenographer → Agent)
    CAPTION_UPDATE = "caption.update"   # 자막 업데이트 알림 (Agent → All)
    CAPTION_MERGED = "caption.merged"   # 병합 완료 알림 (Agent → All)
    CAPTION_SYNC = "caption.sync"       # 자막 동기화 (Agent → Reviewer)
    
    # === STT/OCR 관련 ===
    STT_RESULT = "stt.result"           # STT 결과 (Agent → Stenographers)
    OCR_RESULT = "ocr.result"           # OCR 결과 (Agent → Stenographers)
    
    # === 검수 관련 ===
    REVIEW_EDIT = "review.edit"         # 검수 수정 (Reviewer → Agent)
    REVIEW_APPROVE = "review.approve"   # 검수 승인 (Reviewer → Agent)
    REVIEW_RESULT = "review.result"     # 검수 결과 (Agent → Reviewer)
    
    # === 시스템 관련 ===
    SYSTEM_ERROR = "system.error"       # 에러 알림
    SYSTEM_INFO = "system.info"         # 정보 알림
    PING = "ping"                       # 연결 확인
    PONG = "pong"                       # 연결 확인 응답


@dataclass
class RoomMessage:
    """
    Room 내 메시지 기본 구조
    
    DataChannel을 통해 주고받는 모든 메시지의 기본 형태.
    
    Attributes:
        type: 메시지 타입
        sender: 발신자 identity
        payload: 타입별 페이로드 데이터
        timestamp: 메시지 생성 시각 (Unix timestamp)
        message_id: 메시지 고유 ID (응답 매칭용)
        reply_to: 응답 대상 메시지 ID (응답인 경우)
    """
    type: MessageType
    sender: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: f"{time.time_ns()}")
    reply_to: Optional[str] = None
    
    def to_json(self) -> str:
        """JSON 문자열로 직렬화"""
        return json.dumps({
            "type": self.type.value,
            "sender": self.sender,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "reply_to": self.reply_to,
        }, ensure_ascii=False)
    
    def to_bytes(self) -> bytes:
        """바이트로 직렬화 (DataChannel 전송용)"""
        return self.to_json().encode("utf-8")
    
    @classmethod
    def from_json(cls, json_str: str) -> "RoomMessage":
        """JSON 문자열에서 역직렬화"""
        data = json.loads(json_str)
        return cls(
            type=MessageType(data["type"]),
            sender=data["sender"],
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
            message_id=data.get("message_id", f"{time.time_ns()}"),
            reply_to=data.get("reply_to"),
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "RoomMessage":
        """바이트에서 역직렬화"""
        return cls.from_json(data.decode("utf-8"))


# === 메시지 생성 헬퍼 함수 ===

def create_turn_start_message(
    sender: str,
    turn_id: str,
    holder: str,
    timestamp_ms: int,
) -> RoomMessage:
    """턴 시작 메시지 생성"""
    return RoomMessage(
        type=MessageType.TURN_START,
        sender=sender,
        payload={
            "turn_id": turn_id,
            "holder": holder,
            "timestamp_ms": timestamp_ms,
        },
    )


def create_turn_end_message(
    sender: str,
    turn_id: str,
    timestamp_ms: int,
) -> RoomMessage:
    """턴 종료 메시지 생성"""
    return RoomMessage(
        type=MessageType.TURN_END,
        sender=sender,
        payload={
            "turn_id": turn_id,
            "timestamp_ms": timestamp_ms,
        },
    )


def create_turn_request_message(sender: str) -> RoomMessage:
    """턴 전환 요청 메시지 생성"""
    return RoomMessage(
        type=MessageType.TURN_REQUEST,
        sender=sender,
        payload={},
    )


def create_turn_grant_message(
    sender: str,
    turn_id: str,
    recipient: str,
) -> RoomMessage:
    """턴 권한 부여 메시지 생성"""
    return RoomMessage(
        type=MessageType.TURN_GRANT,
        sender=sender,
        payload={
            "turn_id": turn_id,
            "recipient": recipient,
        },
    )


def create_turn_deny_message(
    sender: str,
    reason: str,
    recipient: str,
) -> RoomMessage:
    """턴 권한 거부 메시지 생성"""
    return RoomMessage(
        type=MessageType.TURN_DENY,
        sender=sender,
        payload={
            "reason": reason,
            "recipient": recipient,
        },
    )


def create_caption_draft_message(
    sender: str,
    segment_id: str,
    turn_id: str,
    timestamp_start_ms: int,
    text: str,
) -> RoomMessage:
    """자막 작성 중 메시지 생성"""
    return RoomMessage(
        type=MessageType.CAPTION_DRAFT,
        sender=sender,
        payload={
            "segment_id": segment_id,
            "turn_id": turn_id,
            "timestamp_start_ms": timestamp_start_ms,
            "text": text,
        },
    )


def create_caption_submit_message(
    sender: str,
    segment_id: str,
    timestamp_end_ms: int,
    text: str,
) -> RoomMessage:
    """자막 제출 메시지 생성"""
    return RoomMessage(
        type=MessageType.CAPTION_SUBMIT,
        sender=sender,
        payload={
            "segment_id": segment_id,
            "timestamp_end_ms": timestamp_end_ms,
            "text": text,
        },
    )


def create_caption_update_message(
    sender: str,
    segment: dict,
) -> RoomMessage:
    """자막 업데이트 알림 메시지 생성"""
    return RoomMessage(
        type=MessageType.CAPTION_UPDATE,
        sender=sender,
        payload={
            "segment": segment,
        },
    )


def create_caption_sync_message(
    sender: str,
    segments: list,
    current_timestamp_ms: int,
) -> RoomMessage:
    """자막 동기화 메시지 생성 (검수자용)"""
    return RoomMessage(
        type=MessageType.CAPTION_SYNC,
        sender=sender,
        payload={
            "segments": segments,
            "current_timestamp_ms": current_timestamp_ms,
        },
    )


def create_stt_result_message(
    sender: str,
    text: str,
    timestamp_ms: int,
    confidence: float,
    is_final: bool = True,
) -> RoomMessage:
    """STT 결과 메시지 생성"""
    return RoomMessage(
        type=MessageType.STT_RESULT,
        sender=sender,
        payload={
            "text": text,
            "timestamp_ms": timestamp_ms,
            "confidence": confidence,
            "is_final": is_final,
        },
    )


def create_ocr_result_message(
    sender: str,
    text: str,
    timestamp_ms: int,
    region: dict,
    confidence: float = 1.0,
) -> RoomMessage:
    """OCR 결과 메시지 생성"""
    return RoomMessage(
        type=MessageType.OCR_RESULT,
        sender=sender,
        payload={
            "text": text,
            "timestamp_ms": timestamp_ms,
            "region": region,
            "confidence": confidence,
        },
    )


def create_review_edit_message(
    sender: str,
    segment_id: str,
    new_text: str,
    note: Optional[str] = None,
) -> RoomMessage:
    """검수 수정 메시지 생성"""
    return RoomMessage(
        type=MessageType.REVIEW_EDIT,
        sender=sender,
        payload={
            "segment_id": segment_id,
            "new_text": new_text,
            "note": note,
        },
    )


def create_review_approve_message(
    sender: str,
    segment_id: str,
) -> RoomMessage:
    """검수 승인 메시지 생성"""
    return RoomMessage(
        type=MessageType.REVIEW_APPROVE,
        sender=sender,
        payload={
            "segment_id": segment_id,
        },
    )


def create_system_error_message(
    sender: str,
    error_code: str,
    error_message: str,
    details: Optional[dict] = None,
) -> RoomMessage:
    """시스템 에러 메시지 생성"""
    return RoomMessage(
        type=MessageType.SYSTEM_ERROR,
        sender=sender,
        payload={
            "error_code": error_code,
            "error_message": error_message,
            "details": details or {},
        },
    )


def create_system_info_message(
    sender: str,
    info_type: str,
    message: str,
    data: Optional[dict] = None,
) -> RoomMessage:
    """시스템 정보 메시지 생성"""
    return RoomMessage(
        type=MessageType.SYSTEM_INFO,
        sender=sender,
        payload={
            "info_type": info_type,
            "message": message,
            "data": data or {},
        },
    )
