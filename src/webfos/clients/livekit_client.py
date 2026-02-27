"""
LiveKit Server API 클라이언트.

룸 생성/삭제, Ingress 관리, 토큰 발급을 담당한다.
livekit-api 라이브러리를 사용하여 LiveKit Server와 통신한다.
"""

from typing import Dict, Any, Optional
from loguru import logger
from livekit import api
from livekit.api.access_token import AccessToken, VideoGrants
from livekit.protocol.ingress import CreateIngressRequest, IngressInput, IngressInfo

from core.config import settings


class LiveKitClient:
    """
    LiveKit Server API 클라이언트.
    
    - create_room(): 룸 생성
    - delete_room(): 룸 삭제
    - create_ingress(): HLS Ingress 생성
    - delete_ingress(): Ingress 삭제
    - generate_token(): 참가자 토큰 발급
    """
    
    def __init__(self):
        self._api: Optional[api.LiveKitAPI] = None
    
    def _get_api(self) -> api.LiveKitAPI:
        """지연 초기화된 LiveKit API 클라이언트"""
        if self._api is None:
            self._api = api.LiveKitAPI(
                settings.livekit_http_url,
                settings.LIVEKIT_API_KEY,
                settings.LIVEKIT_API_SECRET,
            )
        return self._api
    
    async def create_ingress(
        self,
        room_name: str,
        hls_url: str,
        participant_identity: str = "ingress-hls-source",
        participant_name: str = "HLS Source",
        ingress_name: str = "hls-ingress",
    ) -> IngressInfo:
        """
        HLS Ingress 생성.
        
        Args:
            room_name: 대상 룸 이름
            hls_url: HLS 스트림 URL
            participant_identity: Ingress 참가자 ID
            participant_name: Ingress 참가자 이름
            ingress_name: Ingress 이름
            
        Returns:
            IngressInfo: 생성된 Ingress 정보
        """
        lk_api = self._get_api()
        
        request = CreateIngressRequest(
            input_type=IngressInput.URL_INPUT,
            name=ingress_name,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            url=hls_url,
        )
        
        info = await lk_api.ingress.create_ingress(request)
        logger.info(f"[LiveKitClient] Ingress 생성: {info.ingress_id} -> room={room_name}")
        return info
    
    async def delete_ingress(self, ingress_id: str) -> None:
        """Ingress 삭제"""
        from livekit.protocol.ingress import DeleteIngressRequest
        
        lk_api = self._get_api()
        request = DeleteIngressRequest(ingress_id=ingress_id)
        await lk_api.ingress.delete_ingress(request)
        logger.info(f"[LiveKitClient] Ingress 삭제: {ingress_id}")
    
    async def list_ingresses(self, room_name: Optional[str] = None) -> list:
        """Ingress 목록 조회"""
        from livekit.protocol.ingress import ListIngressRequest
        
        lk_api = self._get_api()
        request = ListIngressRequest(room_name=room_name or "")
        response = await lk_api.ingress.list_ingress(request)
        return list(response.items)
    
    async def list_rooms(self, names: Optional[list] = None) -> list:
        """
        [advice from AI] 룸 목록 조회
        
        Args:
            names: 조회할 룸 이름 목록 (없으면 전체 조회)
            
        Returns:
            list: 룸 정보 목록
        """
        from livekit.protocol.room import ListRoomsRequest
        
        lk_api = self._get_api()
        request = ListRoomsRequest(names=names or [])
        response = await lk_api.room.list_rooms(request)
        return list(response.rooms)
    
    async def list_participants(self, room_name: str) -> list:
        """
        [advice from AI] 특정 룸의 참가자 목록 조회
        
        Args:
            room_name: 룸 이름
            
        Returns:
            list: 참가자 정보 목록
        """
        from livekit.protocol.room import ListParticipantsRequest
        
        lk_api = self._get_api()
        request = ListParticipantsRequest(room=room_name)
        response = await lk_api.room.list_participants(request)
        return list(response.participants)
    
    async def wait_for_ingress_active(self, ingress_id: str, timeout: int = 10) -> bool:
        """
        Ingress가 활성화될 때까지 대기.
        
        Args:
            ingress_id: 대기할 Ingress ID
            timeout: 최대 대기 시간 (초)
            
        Returns:
            bool: 활성화 여부
        """
        import asyncio
        from livekit.protocol.ingress import ListIngressRequest, IngressState
        
        lk_api = self._get_api()
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                request = ListIngressRequest(ingress_id=ingress_id)
                response = await lk_api.ingress.list_ingress(request)
                
                if response.items:
                    ingress = response.items[0]
                    state = ingress.state
                    
                    # ENDPOINT_PUBLISHING (4) 또는 ENDPOINT_BUFFERING (2)이면 활성화됨
                    if state and state.status in (
                        IngressState.Status.ENDPOINT_BUFFERING,
                        IngressState.Status.ENDPOINT_PUBLISHING,
                    ):
                        logger.info(f"[LiveKitClient] Ingress 활성화됨: {ingress_id}")
                        return True
                    
                    logger.debug(f"[LiveKitClient] Ingress 상태: {state.status if state else 'unknown'}")
                    
            except Exception as e:
                logger.warning(f"[LiveKitClient] Ingress 상태 확인 실패: {e}")
            
            await asyncio.sleep(0.5)
        
        logger.warning(f"[LiveKitClient] Ingress 활성화 타임아웃: {ingress_id}")
        return False
    
    def generate_token(
        self,
        room_name: str,
        identity: str,
        name: Optional[str] = None,
        can_publish: bool = False,
        can_subscribe: bool = True,
    ) -> str:
        """
        참가자 JWT 토큰 발급.
        
        Args:
            room_name: 룸 이름
            identity: 참가자 고유 ID
            name: 참가자 표시 이름
            can_publish: 미디어 발행 권한
            can_subscribe: 미디어 구독 권한
            
        Returns:
            str: JWT 토큰
        """
        token = (
            AccessToken(
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET,
            )
            .with_identity(identity)
            .with_name(name or identity)
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
            ))
        )
        return token.to_jwt()
    
    async def dispatch_agent(
        self,
        room_name: str,
        agent_name: str = "room-agent",
        metadata: str = "",
    ) -> None:
        """
        [advice from AI] Room에 Agent를 dispatch.
        
        livekit-agents Worker가 실행 중이어야 dispatch가 처리된다.
        Worker가 없으면 dispatch 요청만 대기 상태로 남는다.
        """
        from livekit.api import CreateAgentDispatchRequest

        lk_api = self._get_api()
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=metadata,
            )
        )
        logger.info(f"[LiveKitClient] Agent dispatch: {agent_name} -> room={room_name}")
        return dispatch

    async def close(self):
        """리소스 정리"""
        if self._api:
            await self._api.aclose()
            self._api = None


# 싱글톤 인스턴스
livekit_client = LiveKitClient()
