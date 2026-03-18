"""
Participant Handler - 참가자 관리 전담 모듈.

RoomAgent에서 분리된 참가자 등록/해제 로직을 담당합니다.
- 참가자 등록/해제
- 속기사 목록 브로드캐스트

[advice from AI] RoomAgent 리팩토링 Phase 2
"""

import asyncio
import json
from typing import Optional, Dict, Callable, Awaitable, List, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from livekit import rtc
    from .turn_manager import TurnManager


class ParticipantHandler:
    """
    참가자 관리 핸들러.
    
    참가자 등록/해제, 속기사 목록 관리를 담당합니다.
    RoomAgent와 협력하여 동작하며, 필요한 콜백과 상태를 주입받습니다.
    """
    
    INGRESS_IDENTITY = "ingress-hls-source"
    
    def __init__(
        self,
        turn_manager: "TurnManager",
        get_stenographer_texts: Callable[[], Dict[str, str]],
        set_stenographer_text: Callable[[str, str], None],
        remove_stenographer_text: Callable[[str], None],
        send_raw_message: Callable[[dict], Awaitable[None]],
        broadcast_turn_state: Callable[[], Awaitable[None]],
        start_turn: Callable[[str], Awaitable[Optional[object]]],
        get_current_timestamp: Callable[[], int],
        get_broadcast_text: Callable[[], str],
        set_broadcast_text: Callable[[str], None],
        stop_stt: Callable[[], Awaitable[None]],
        get_stt_enabled: Callable[[], bool],
        cancel_stt_stream_task: Callable[[], Awaitable[None]],
    ):
        """
        Args:
            turn_manager: 턴 관리자 인스턴스
            get_stenographer_texts: 속기사별 텍스트 dict 반환 함수
            set_stenographer_text: 속기사 텍스트 설정 함수
            remove_stenographer_text: 속기사 텍스트 삭제 함수
            send_raw_message: 메시지 전송 함수
            broadcast_turn_state: 턴 상태 브로드캐스트 함수
            start_turn: 턴 시작 함수
            get_current_timestamp: 현재 타임스탬프 반환 함수
            get_broadcast_text: 송출 텍스트 반환 함수
            set_broadcast_text: 송출 텍스트 설정 함수
            stop_stt: STT 중지 함수
            get_stt_enabled: STT 활성화 여부 반환 함수
            cancel_stt_stream_task: STT 스트림 태스크 취소 함수
        """
        self._turn_manager = turn_manager
        self._get_stenographer_texts = get_stenographer_texts
        self._set_stenographer_text = set_stenographer_text
        self._remove_stenographer_text = remove_stenographer_text
        self._send_raw_message = send_raw_message
        self._broadcast_turn_state = broadcast_turn_state
        self._start_turn = start_turn
        self._get_current_timestamp = get_current_timestamp
        self._get_broadcast_text = get_broadcast_text
        self._set_broadcast_text = set_broadcast_text
        self._stop_stt = stop_stt
        self._get_stt_enabled = get_stt_enabled
        self._cancel_stt_stream_task = cancel_stt_stream_task
        
        logger.info("[ParticipantHandler] 초기화 완료")
    
    async def register_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """
        참가자 등록
        
        participant metadata에서 role 정보를 추출하여 TurnManager에 등록한다.
        metadata 형식: {"role": "stenographer" | "reviewer", "name": "..."}
        """
        identity = participant.identity
        
        # 시스템 참가자 필터링
        if identity == self.INGRESS_IDENTITY:
            return
        if identity.startswith("agent-"):
            logger.debug(f"[ParticipantHandler] Agent identity 무시: {identity}")
            return
        
        role = "stenographer"
        name = identity
        
        if participant.metadata:
            try:
                meta = json.loads(participant.metadata)
                role = meta.get("role", "stenographer")
                name = meta.get("name", identity)
            except (json.JSONDecodeError, TypeError):
                pass
        
        success = self._turn_manager.register_participant(identity, role, name)
        if success:
            logger.info(f"[ParticipantHandler] 참가자 등록 완료: {identity} ({role})")
            
            if role == "stenographer":
                # 텍스트 상태 초기화
                self._set_stenographer_text(identity, "")
                
                await self.broadcast_stenographer_list()
                
                # 송출 권한 로직
                current_holder = self._turn_manager.get_current_holder()
                registered_stenos = [s.identity for s in self._turn_manager.get_stenographers()]
                
                holder_is_valid = current_holder and current_holder in registered_stenos
                
                if not holder_is_valid:
                    if registered_stenos:
                        first_steno = registered_stenos[0]
                        # 기존 턴이 있으면 종료
                        if self._turn_manager._current_turn:
                            current_ts = self._get_current_timestamp()
                            await self._turn_manager.end_turn(current_ts)
                        
                        turn = await self._start_turn(first_steno)
                        if turn:
                            logger.info(f"[ParticipantHandler] 송출 권한 부여 (첫 번째 속기사): {first_steno}")
                        else:
                            logger.error(f"[ParticipantHandler] 송출 권한 부여 실패: {first_steno}")
                else:
                    logger.info(f"[ParticipantHandler] 기존 송출 권한 보유자: {current_holder}")
                
                # 모든 참가자에게 현재 턴 상태 브로드캐스트
                await self._broadcast_turn_state()
                
                # 신규 참가자에게 현재 송출 텍스트 전송
                broadcast_text = self._get_broadcast_text()
                if broadcast_text:
                    await self._send_raw_message({
                        "type": "caption.broadcast",
                        "text": broadcast_text,
                        "sender": "system",
                    })
    
    async def unregister_participant(
        self,
        participant: "rtc.RemoteParticipant",
    ) -> None:
        """참가자 등록 해제"""
        identity = participant.identity
        
        # 시스템 참가자 필터링
        if identity == self.INGRESS_IDENTITY:
            return
        if identity.startswith("agent-"):
            return
        
        was_turn_holder = self._turn_manager.get_current_holder() == identity
        was_stenographer = identity in [
            p.identity for p in self._turn_manager.get_stenographers()
        ]
        
        # 먼저 참가자 해제
        self._turn_manager.unregister_participant(identity)
        
        # 속기사였으면 텍스트 상태 삭제
        if was_stenographer:
            self._remove_stenographer_text(identity)
        
        # 턴 보유자였으면 다음 속기사에게 전환
        if was_turn_holder:
            current_ts = self._get_current_timestamp()
            
            # 먼저 현재 턴 종료
            if self._turn_manager._current_turn and self._turn_manager._current_turn.is_active():
                await self._turn_manager.end_turn(current_ts)
                logger.info(f"[ParticipantHandler] 턴 종료 (퇴장자: {identity})")
            
            # 남은 속기사 확인
            remaining = self._turn_manager.get_stenographers()
            if remaining:
                turn = await self._turn_manager.start_turn(remaining[0].identity, current_ts)
                if turn:
                    logger.info(f"[ParticipantHandler] 턴 승계 완료: {remaining[0].identity}")
                else:
                    logger.error(f"[ParticipantHandler] 턴 승계 실패: {remaining[0].identity}")
            else:
                logger.info("[ParticipantHandler] 모든 속기사 퇴장, 턴 종료")
        
        # 속기사였으면 목록/턴 브로드캐스트
        if was_stenographer:
            await self.broadcast_stenographer_list()
            await self._broadcast_turn_state()
            
            # 모든 속기사 퇴장 시 송출 텍스트 리셋 및 STT 중지
            remaining_stenos = self._turn_manager.get_stenographers()
            if not remaining_stenos:
                self._set_broadcast_text("")
                logger.info("[ParticipantHandler] 모든 속기사 퇴장, 송출 텍스트 리셋")
                
                # STT 활성화 상태면 중지
                if self._get_stt_enabled():
                    await self._cancel_stt_stream_task()
                    await self._stop_stt()
                    await self._send_raw_message({
                        "type": "stt.status",
                        "enabled": False,
                        "message": "all_stenographers_left",
                    })
                    logger.info("[ParticipantHandler] 모든 속기사 퇴장, STT 중지")
            
            logger.info(f"[ParticipantHandler] 속기사 퇴장 처리 완료: {identity}")
    
    async def broadcast_stenographer_list(self) -> None:
        """
        속기사 목록 브로드캐스트 (현재 텍스트 상태 포함)
        """
        stenographers = self._turn_manager.get_stenographers()
        steno_texts = self._get_stenographer_texts()
        steno_list = [
            {
                "identity": s.identity, 
                "text": steno_texts.get(s.identity, "")
            } 
            for s in stenographers
        ]
        
        message = {
            "type": "stenographer.list",
            "stenographers": steno_list,
        }
        
        await self._send_raw_message(message)
        logger.info(f"[ParticipantHandler] 속기사 목록 브로드캐스트: {len(steno_list)}명")
