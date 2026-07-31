from datetime import datetime
from bson import ObjectId
from src.mongo import get_db

ROLES = ['admin', 'operator', 'viewer']


class UserTemplate:
    """使用者模板 — 定義角色權限，可指派給使用者"""
    COLLECTION = 'user_templates'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def ensure_defaults(cls) -> str:
        """
        確保系統預設「管理者」模板存在（is_system=True、role='admin'）。
        回傳模板 ID。
        """
        admin_tmpl = cls._col().find_one({'is_system': True, 'role': 'admin'})
        if not admin_tmpl:
            result = cls._col().insert_one({
                'name':        '管理者',
                'description': '系統預設管理者模板，不可刪除',
                'role':        'admin',
                'is_system':   True,
                'created_at':  datetime.utcnow(),
            })
            return str(result.inserted_id)
        return str(admin_tmpl['_id'])

    @classmethod
    def find_all(cls) -> list:
        # 系統模板排最前
        docs = cls._col().find({}, sort=[('is_system', -1), ('name', 1)])
        return [cls._serialize(d) for d in docs]

    @classmethod
    def find_by_id(cls, tid) -> dict | None:
        try:
            doc = cls._col().find_one({'_id': ObjectId(str(tid))})
            return cls._serialize(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def create(cls, name: str, role: str = 'viewer',
               description: str = '') -> str:
        result = cls._col().insert_one({
            'name':        name,
            'role':        role,
            'description': description,
            'is_system':   False,
            'created_at':  datetime.utcnow(),
        })
        return str(result.inserted_id)

    @classmethod
    def update(cls, tid: str, name: str = None, description: str = None,
               role: str = None) -> bool:
        upd = {}
        if name        is not None: upd['name']        = name
        if description is not None: upd['description'] = description
        if role        is not None: upd['role']        = role
        if not upd:
            return False
        result = cls._col().update_one({'_id': ObjectId(tid)}, {'$set': upd})
        return result.matched_count > 0

    @classmethod
    def delete(cls, tid: str) -> str:
        """
        回傳值：
          'ok'        — 刪除成功
          'system'    — 系統預設模板，不可刪除
          'not_found' — 找不到
        """
        try:
            doc = cls._col().find_one({'_id': ObjectId(tid)}, {'is_system': 1})
        except Exception:
            return 'not_found'
        if not doc:
            return 'not_found'
        if doc.get('is_system'):
            return 'system'
        result = cls._col().delete_one({'_id': ObjectId(tid)})
        return 'ok' if result.deleted_count > 0 else 'not_found'

    @staticmethod
    def _serialize(doc: dict) -> dict:
        if not doc:
            return {}
        created = doc.get('created_at')
        return {
            '_id':         str(doc['_id']),
            'name':        doc.get('name', ''),
            'role':        doc.get('role', 'viewer'),
            'description': doc.get('description', ''),
            'is_system':   doc.get('is_system', False),
            'created_at':  created.isoformat() if created else '',
        }
