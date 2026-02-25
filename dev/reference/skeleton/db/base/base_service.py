"""
트랜잭션 관리 베이스 서비스 — 모든 도메인 DB 서비스가 상속하는 베이스.

Repository를 래핑하여 트랜잭션 경계를 관리한다.
모든 쓰기 연산은 transaction() 컨텍스트 내에서 실행된다.

[도메인 DB 서비스 작성법]
class FeedbackService(BaseService[Feedback]):
    def __init__(self, db: Session):
        repo = FeedbackRepository(db)
        super().__init__(repo, db)
        self.feedback_repo = repo

    def save_feedback(self, data: Dict) -> Optional[Feedback]:
        with self.transaction():
            return self.feedback_repo.create(data)
"""

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from loguru import logger
from typing import Any, Dict, List, Optional, TypeVar, Generic

from db.base.base_repository import BaseRepository

T = TypeVar('T')


class BaseService(Generic[T]):
    """트랜잭션 컨텍스트 관리 + 공통 CRUD 래퍼"""

    def __init__(self, repository: BaseRepository[T], db_session: Session):
        self.repository = repository
        self.db = db_session

    @contextmanager
    def transaction(self):
        """트랜잭션 컨텍스트 매니저 — 실패 시 자동 rollback"""
        try:
            yield
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"[BaseService] Transaction error: {str(e)}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"[BaseService] Unexpected error in transaction: {str(e)}")
            raise

    # === CRUD 래퍼 (트랜잭션 포함) ===

    def create(self, obj_data: Dict[str, Any]) -> T:
        with self.transaction():
            return self.repository.create(obj_data)

    def get_by_id(self, obj_id: Any) -> Optional[T]:
        return self.repository.get_by_id(obj_id)

    def get_obj_by_id(self, key: str, value: Any) -> Optional[T]:
        return self.repository.get_obj_by_id(key, value)

    def get_all(self) -> List[T]:
        return self.repository.get_all()

    def update(self, obj_id: Any, update_data: Dict[str, Any]) -> Optional[T]:
        with self.transaction():
            return self.repository.update(obj_id, update_data)

    def bulk_create(self, obj_list: List[Dict[str, Any]]) -> List[T]:
        with self.transaction():
            return self.repository.bulk_create(obj_list)

    def bulk_upsert(self, objs: List[Dict[str, Any]], unique_fields: List[str]) -> int:
        with self.transaction():
            return self.repository.bulk_upsert(objs, unique_fields)

    def delete_obj(self, obj_id: Any) -> Optional[T]:
        with self.transaction():
            return self.repository.delete_obj(obj_id=obj_id)

    def get_obj_by_keys(self, filters: Dict[str, Any]) -> Optional[T]:
        return self.repository.get_obj_by_keys(filters)

    def get_all_objs_by_keys(self, filters: Dict[str, Any]) -> List[T]:
        return self.repository.get_all_objs_by_keys(filters)
