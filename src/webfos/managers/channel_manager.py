"""
채널 관리 매니저.

하드코딩된 채널 목록 관리 (추후 DB 연동으로 확장 예정).
"""

from typing import Dict, List, Optional
import asyncio
from dataclasses import dataclass
from loguru import logger


@dataclass
class Channel:
    """채널 정보"""
    id: str
    name: str
    hls_url: str
    description: str = ""
    ingress_id: Optional[str] = None
    room_name: Optional[str] = None
    is_active: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "hls_url": self.hls_url,
            "description": self.description,
            "is_active": self.is_active,
        }


class ChannelManager:
    """
    채널 관리 싱글톤 매니저.
    
    현재는 하드코딩된 목록, 추후 DB 연동으로 확장.
    """
    
    def __init__(self):
        # 하드코딩된 채널 목록 (추후 DB로 이동)
        self._channels: Dict[str, Channel] = {}
        self._init_default_channels()
    
    def _init_default_channels(self):
        """기본 채널 목록 초기화"""
        default_channels = [
            Channel(
                id="wowtv",
                name="한국경제TV",
                hls_url="https://cdnlive.wowtv.co.kr/wowtvlive/livestream/playlist.m3u8",
                description="한국경제TV 실시간 방송",
            ),
            Channel(
                id="lotteone",
                name="롯데원TV",
                hls_url="https://onetvhlslive.lotteimall.com/lotteonetvlive/lotteonetvlive.mp4.m3u8",
                description="롯데원TV 실시간 방송",
            ),
            Channel(
                id="cjonstyle",
                name="CJ온스타일",
                hls_url="https://live-ch1.cjonstyle.net/cjmalllive/stream2/playlist.m3u8",
                description="CJ온스타일 실시간 방송",
            ),
            Channel(
                id="ebs2",
                name="EBS 2TV",
                hls_url="https://ebsonair.ebs.co.kr/ebs2familypc/familypc1m/playlist.m3u8",
                description="EBS 2TV 실시간 방송",
            ),
            Channel(
                id="chmbc",
                name="춘천MBC",
                hls_url="https://stream.chmbc.co.kr/TV/myStream/playlist.m3u8",
                description="춘천MBC 실시간 방송",
            ),
            Channel(
                id="knn",
                name="KNN",
                hls_url="https://stream1.knn.co.kr/hls/9ly4534y7dm2xfa123r2_tv/index.m3u8",
                description="KNN 실시간 방송",
            ),
        ]
        
        for channel in default_channels:
            self._channels[channel.id] = channel
        
        logger.info(f"[ChannelManager] {len(self._channels)}개 채널 초기화")
    
    def get_channel(self, channel_id: str) -> Optional[Channel]:
        """채널 조회"""
        return self._channels.get(channel_id)
    
    def list_channels(self) -> List[Channel]:
        """전체 채널 목록"""
        return list(self._channels.values())
    
    def add_channel(self, channel: Channel) -> bool:
        """채널 추가 (런타임)"""
        if channel.id in self._channels:
            logger.warning(f"[ChannelManager] 채널 이미 존재: {channel.id}")
            return False
        self._channels[channel.id] = channel
        logger.info(f"[ChannelManager] 채널 추가: {channel.id}")
        return True
    
    def remove_channel(self, channel_id: str) -> bool:
        """채널 제거"""
        if channel_id in self._channels:
            del self._channels[channel_id]
            logger.info(f"[ChannelManager] 채널 제거: {channel_id}")
            return True
        return False
    
    def set_channel_ingress(
        self, 
        channel_id: str, 
        ingress_id: str, 
        room_name: str,
        is_active: bool = True
    ):
        """채널에 Ingress 정보 설정"""
        channel = self._channels.get(channel_id)
        if channel:
            channel.ingress_id = ingress_id
            channel.room_name = room_name
            channel.is_active = is_active
            logger.info(f"[ChannelManager] 채널 Ingress 설정: {channel_id} -> {ingress_id}")
    
    def get_active_channels(self) -> List[Channel]:
        """활성화된 채널 목록"""
        return [ch for ch in self._channels.values() if ch.is_active]
    
    async def _create_single_ingress(self, channel: Channel) -> bool:
        """
        단일 채널의 Ingress 생성.
        
        Returns:
            bool: 성공 여부
        """
        from clients.livekit_client import livekit_client
        
        try:
            room_name = f"channel-{channel.id}"
            
            # 기존 Ingress 삭제
            existing = await livekit_client.list_ingresses(room_name)
            for old_ingress in existing:
                try:
                    await livekit_client.delete_ingress(old_ingress.ingress_id)
                    logger.debug(f"[ChannelManager] 기존 Ingress 삭제: {old_ingress.ingress_id}")
                except Exception:
                    pass
            
            # 새 Ingress 생성
            ingress_info = await livekit_client.create_ingress(
                room_name=room_name,
                hls_url=channel.hls_url,
                participant_identity="ingress-hls-source",
                participant_name="HLS Source",
                ingress_name=f"ingress-{channel.id}",
            )
            
            self.set_channel_ingress(
                channel.id,
                ingress_info.ingress_id,
                room_name,
                is_active=True
            )
            
            # [advice from AI] Ingress 생성 후 Agent dispatch
            try:
                await livekit_client.dispatch_agent(
                    room_name=room_name,
                    agent_name="room-agent",
                    metadata=f'{{"channel_id": "{channel.id}", "channel_name": "{channel.name}"}}',
                )
            except Exception as e:
                logger.warning(f"[ChannelManager] Agent dispatch 실패 (Worker 미실행?): {channel.id} - {e}")
            
            logger.info(f"[ChannelManager] Ingress 생성: {channel.id} -> {ingress_info.ingress_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ChannelManager] 채널 {channel.id} Ingress 생성 실패: {e}")
            channel.is_active = False
            return False
    
    async def initialize_all_ingresses(self, batch_size: int = 5):
        """
        모든 채널의 Ingress를 병렬로 초기화.
        
        Args:
            batch_size: 동시에 생성할 Ingress 수 (기본: 5)
        """
        channels = list(self._channels.values())
        total = len(channels)
        logger.info(f"[ChannelManager] {total}개 채널 Ingress 병렬 초기화 시작 (배치: {batch_size})")
        
        # 배치 단위로 병렬 생성
        for i in range(0, total, batch_size):
            batch = channels[i:i + batch_size]
            tasks = [self._create_single_ingress(ch) for ch in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"[ChannelManager] 배치 {i // batch_size + 1} 완료 ({len(batch)}개)")
        
        active_count = len(self.get_active_channels())
        logger.info(f"[ChannelManager] Ingress 초기화 완료: {active_count}/{total} 활성화")

    async def cleanup_all_ingresses(self):
        """
        [advice from AI] 모든 채널의 Ingress를 삭제 — 서버 종료 시 좀비 방지.
        """
        from clients.livekit_client import livekit_client
        
        active_channels = [ch for ch in self._channels.values() if ch.ingress_id]
        if not active_channels:
            logger.info("[ChannelManager] 삭제할 Ingress 없음")
            return
        
        logger.info(f"[ChannelManager] {len(active_channels)}개 채널 Ingress 삭제 시작")
        
        for channel in active_channels:
            try:
                await livekit_client.delete_ingress(channel.ingress_id)
                logger.info(f"[ChannelManager] Ingress 삭제: {channel.id} -> {channel.ingress_id}")
            except Exception as e:
                logger.warning(f"[ChannelManager] Ingress 삭제 실패: {channel.id} - {e}")
            finally:
                channel.ingress_id = None
                channel.room_name = None
                channel.is_active = False
        
        logger.info("[ChannelManager] 모든 Ingress 삭제 완료")


# 싱글톤 인스턴스
channel_manager = ChannelManager()
