"""
Generic CRUD 레포지토리 — 모든 도메인 레포지토리가 상속하는 베이스.

[제공 메서드]
- create / get_by_id / update / delete_obj         (단건 CRUD)
- bulk_create / bulk_upsert                         (벌크 연산)
- get_obj_by_id / get_obj_by_keys / get_all_objs_by_keys  (동적 필터 조회)
- upsert                                           (단건 Upsert)

[도메인 레포지토리 작성법]
class FeedbackRepository(BaseRepository[Feedback]):
    def __init__(self, db: Session):
        super().__init__(db, Feedback)

    def get_recent(self, limit: int) -> List[Feedback]:
        # 도메인 특화 쿼리를 여기에 추가
        ...
"""

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from loguru import logger
import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic

T = TypeVar('T')


def safe_equals(old_value: Any, new_value: Any) -> bool:
    """datetime <-> str 등 타입이 달라도 실질적 값이 같으면 True"""
    if isinstance(old_value, datetime.datetime) and isinstance(new_value, str):
        try:
            new_dt = datetime.datetime.fromisoformat(new_value)
            if new_dt.tzinfo is None:
                new_dt = new_dt.replace(tzinfo=datetime.timezone.utc)
            old_dt = old_value
            if old_dt.tzinfo is None:
                old_dt = old_dt.replace(tzinfo=datetime.timezone.utc)
            return old_dt == new_dt
        except Exception:
            return False
    if isinstance(old_value, str) and isinstance(new_value, datetime.datetime):
        try:
            old_dt = datetime.datetime.fromisoformat(old_value)
            if old_dt.tzinfo is None:
                old_dt = old_dt.replace(tzinfo=datetime.timezone.utc)
            new_dt = new_value
            if new_dt.tzinfo is None:
                new_dt = new_dt.replace(tzinfo=datetime.timezone.utc)
            return old_dt == new_dt
        except Exception:
            return False
    if isinstance(old_value, datetime.datetime) and isinstance(new_value, datetime.datetime):
        od = old_value if old_value.tzinfo else old_value.replace(tzinfo=datetime.timezone.utc)
        nd = new_value if new_value.tzinfo else new_value.replace(tzinfo=datetime.timezone.utc)
        return od == nd
    return old_value == new_value


class BaseRepository(Generic[T]):
    """공통 CRUD/Upsert/BulkInsert 베이스 레포지토리"""

    def __init__(self, db: Session, model: type):
        self.db = db
        self.model = model

    # === 단건 CRUD ===

    def create(self, obj_data: Dict[str, Any]) -> T:
        """단일 객체 생성"""
        instance = self.model(**obj_data)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def get_by_id(self, obj_id: Any) -> Optional[T]:
        """PK로 단일 객체 조회"""
        return self.db.query(self.model).get(obj_id)

    def get_obj_by_id(self, key: str, value: Any) -> Optional[T]:
        """특정 컬럼 값으로 단일 객체 조회"""
        column = getattr(self.model, key)
        return self.db.query(self.model).filter(column == value).first()

    def get_all(self) -> List[T]:
        """모든 객체 조회 (created_at 내림차순, 없으면 기본)"""
        if hasattr(self.model, 'created_at'):
            return self.db.query(self.model).order_by(self.model.created_at.desc()).all()
        return self.db.query(self.model).all()

    def update(self, obj_id: Any, update_data: Dict[str, Any]) -> Optional[T]:
        """PK로 객체 업데이트 — 값이 실제로 변경된 경우에만 commit"""
        obj = self.get_by_id(obj_id)
        if not obj:
            return None
        changed = False
        for key, value in update_data.items():
            old_value = getattr(obj, key, None)
            if not safe_equals(old_value, value):
                setattr(obj, key, value)
                changed = True
        if changed:
            self.db.commit()
            self.db.refresh(obj)
            return obj
        return None

    def delete_obj(self, obj_id: Any) -> Optional[T]:
        """PK로 객체 삭제"""
        obj = self.get_by_id(obj_id)
        if not obj:
            return None
        self.db.delete(obj)
        self.db.commit()
        return obj

    # === 벌크 연산 ===

    def bulk_create(self, obj_list: List[Dict[str, Any]]) -> List[T]:
        """여러 객체 일괄 생성"""
        instances = [self.model(**item) for item in obj_list]
        self.db.bulk_save_objects(instances)
        self.db.commit()
        return instances

    def upsert(self, where: Dict[str, Any], update_data: Dict[str, Any]) -> T:
        """단건 Upsert — 존재하면 업데이트, 없으면 생성"""
        obj = self.db.query(self.model).filter_by(**where).first()
        if obj:
            for k, v in update_data.items():
                setattr(obj, k, v)
        else:
            obj = self.model(**{**where, **update_data})
            self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def bulk_upsert(self, objs: List[Dict[str, Any]], unique_fields: List[str]) -> int:
        """
        Bulk Upsert (PostgreSQL ON CONFLICT).
        unique_fields 기준 충돌 시 update, 아니면 insert.
        """
        if not objs:
            return 0
        stmt = pg_insert(self.model).values(objs)
        valid_keys = set(objs[0].keys())
        update_dict = {
            c.name: getattr(stmt.excluded, c.name)
            for c in self.model.__table__.columns
            if c.name not in unique_fields and c.name != "id" and c.name in valid_keys
        }
        if update_dict:
            stmt = stmt.on_conflict_do_update(index_elements=unique_fields, set_=update_dict)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=unique_fields)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    # === 동적 필터 조회 ===

    def get_obj_by_keys(self, filters: Dict[str, Any]) -> Optional[T]:
        """필터 조건으로 단일 객체 조회"""
        q = self.db.query(self.model)
        for key, value in filters.items():
            column = getattr(self.model, key)
            if isinstance(value, list):
                q = q.filter(column.in_(value))
            else:
                q = q.filter(column == value)
        return q.first()

    def get_all_objs_by_keys(self, filters: Dict[str, Any]) -> List[T]:
        """필터 조건으로 여러 객체 조회 (AND 조건)"""
        q = self.db.query(self.model)
        for key, value in filters.items():
            if not hasattr(self.model, key):
                continue
            column = getattr(self.model, key)
            if value is not None:
                if isinstance(value, list):
                    if None in value:
                        from sqlalchemy import or_
                        clean_values = [v for v in value if v is not None]
                        if clean_values:
                            q = q.filter(or_(column.in_(clean_values), column.is_(None)))
                        else:
                            q = q.filter(column.is_(None))
                    else:
                        q = q.filter(column.in_(value))
                else:
                    q = q.filter(column == value)
        return q.all()
