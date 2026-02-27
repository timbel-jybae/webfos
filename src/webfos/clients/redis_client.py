"""
[advice from AI] Redis 클라이언트 — RoomAgent 상태 공유용

RoomAgent와 Admin API 간 상태 공유를 위한 Redis 클라이언트.
- TTL 기반 자동 만료
- 키 패턴 기반 초기화
- JSON 직렬화/역직렬화
"""

import json
from typing import Any, Dict, List, Optional
from loguru import logger
import redis.asyncio as redis

from core.config import settings


class RedisKeys:
    """
    [advice from AI] Redis 키 네이밍 헬퍼
    
    키 구조:
    - webfos:room:{room_name}:state - 룸 전체 상태 (JSON)
    - webfos:room:{room_name}:history - 송출 이력 (List)
    """
    
    PREFIX = settings.REDIS_KEY_PREFIX
    
    @classmethod
    def room_state(cls, room_name: str) -> str:
        """룸 상태 키"""
        return f"{cls.PREFIX}:room:{room_name}:state"
    
    @classmethod
    def room_history(cls, room_name: str) -> str:
        """룸 송출 이력 키"""
        return f"{cls.PREFIX}:room:{room_name}:history"
    
    @classmethod
    def all_pattern(cls) -> str:
        """전체 키 패턴 (초기화용)"""
        return f"{cls.PREFIX}:*"


class RedisClient:
    """
    [advice from AI] Redis 비동기 클라이언트
    
    사용법:
        await redis_client.connect()
        await redis_client.set_room_state(room_name, state_dict)
        state = await redis_client.get_room_state(room_name)
        await redis_client.close()
    """
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Redis 연결"""
        if self._connected:
            return True
        
        try:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
            )
            
            await self._client.ping()
            self._connected = True
            logger.info(
                f"[RedisClient] 연결 성공: {settings.REDIS_HOST}:{settings.REDIS_PORT}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[RedisClient] 연결 실패: {e}")
            self._client = None
            self._connected = False
            return False
    
    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            logger.info("[RedisClient] 연결 종료")
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    async def _ensure_connected(self) -> bool:
        """연결 확인 및 재연결"""
        if not self._connected:
            return await self.connect()
        return True
    
    # === 룸 상태 관리 ===
    
    async def set_room_state(
        self,
        room_name: str,
        state: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        [advice from AI] 룸 상태 저장
        
        Args:
            room_name: 룸 이름
            state: 상태 딕셔너리
            ttl: TTL (초), None이면 기본값 사용
        """
        if not await self._ensure_connected():
            return False
        
        try:
            key = RedisKeys.room_state(room_name)
            value = json.dumps(state, ensure_ascii=False)
            ex = ttl or settings.REDIS_STATE_TTL
            
            await self._client.set(key, value, ex=ex)
            logger.debug(f"[RedisClient] 룸 상태 저장: {room_name}")
            return True
            
        except Exception as e:
            logger.error(f"[RedisClient] 룸 상태 저장 실패: {e}")
            return False
    
    async def get_room_state(self, room_name: str) -> Optional[Dict[str, Any]]:
        """
        [advice from AI] 룸 상태 조회
        """
        if not await self._ensure_connected():
            return None
        
        try:
            key = RedisKeys.room_state(room_name)
            value = await self._client.get(key)
            
            if value:
                return json.loads(value)
            return None
            
        except Exception as e:
            logger.error(f"[RedisClient] 룸 상태 조회 실패: {e}")
            return None
    
    async def delete_room_state(self, room_name: str) -> bool:
        """룸 상태 삭제"""
        if not await self._ensure_connected():
            return False
        
        try:
            key = RedisKeys.room_state(room_name)
            await self._client.delete(key)
            logger.debug(f"[RedisClient] 룸 상태 삭제: {room_name}")
            return True
            
        except Exception as e:
            logger.error(f"[RedisClient] 룸 상태 삭제 실패: {e}")
            return False
    
    # === 송출 이력 관리 ===
    
    async def add_broadcast_history(
        self,
        room_name: str,
        entry: Dict[str, Any],
        max_length: int = 100,
    ) -> bool:
        """
        [advice from AI] 송출 이력 추가 (최신이 앞)
        
        Args:
            room_name: 룸 이름
            entry: 이력 항목 { text, sender, timestamp }
            max_length: 최대 보관 개수
        """
        if not await self._ensure_connected():
            return False
        
        try:
            key = RedisKeys.room_history(room_name)
            value = json.dumps(entry, ensure_ascii=False)
            
            pipe = self._client.pipeline()
            pipe.lpush(key, value)
            pipe.ltrim(key, 0, max_length - 1)
            pipe.expire(key, settings.REDIS_HISTORY_TTL)
            await pipe.execute()
            
            logger.debug(f"[RedisClient] 송출 이력 추가: {room_name}")
            return True
            
        except Exception as e:
            logger.error(f"[RedisClient] 송출 이력 추가 실패: {e}")
            return False
    
    async def get_broadcast_history(
        self,
        room_name: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        [advice from AI] 송출 이력 조회 (최신순)
        """
        if not await self._ensure_connected():
            return []
        
        try:
            key = RedisKeys.room_history(room_name)
            values = await self._client.lrange(key, 0, limit - 1)
            
            return [json.loads(v) for v in values]
            
        except Exception as e:
            logger.error(f"[RedisClient] 송출 이력 조회 실패: {e}")
            return []
    
    # === 초기화 ===
    
    async def cleanup_all(self) -> int:
        """
        [advice from AI] 모든 webfos:* 키 삭제 (서버 시작 시 호출)
        
        Returns:
            삭제된 키 수
        """
        if not await self._ensure_connected():
            return 0
        
        try:
            pattern = RedisKeys.all_pattern()
            cursor = 0
            deleted = 0
            
            while True:
                cursor, keys = await self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            
            logger.info(f"[RedisClient] 초기화 완료: {deleted}개 키 삭제")
            return deleted
            
        except Exception as e:
            logger.error(f"[RedisClient] 초기화 실패: {e}")
            return 0
    
    async def cleanup_room(self, room_name: str) -> bool:
        """특정 룸의 모든 키 삭제"""
        if not await self._ensure_connected():
            return False
        
        try:
            keys = [
                RedisKeys.room_state(room_name),
                RedisKeys.room_history(room_name),
            ]
            await self._client.delete(*keys)
            logger.debug(f"[RedisClient] 룸 데이터 삭제: {room_name}")
            return True
            
        except Exception as e:
            logger.error(f"[RedisClient] 룸 데이터 삭제 실패: {e}")
            return False


# 싱글톤 인스턴스
redis_client = RedisClient()
