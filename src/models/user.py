from datetime import datetime
from bson import ObjectId
import bcrypt
from src.mongo import get_db

ROLES = ['admin', 'operator', 'viewer']

_UNSET = object()   # sentinel — 區分「未傳入」與「傳入 None / ''」


class User:
    COLLECTION = 'users'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def find_all(cls) -> list:
        users = cls._col().find({}, {'password': 0})
        result = []
        for u in users:
            doc = {'_id': str(u['_id'])}
            for k, v in u.items():
                if k == '_id':
                    continue
                if k == 'template_id' and v:
                    doc[k] = str(v)
                else:
                    doc[k] = v
            result.append(doc)
        return result

    @classmethod
    def find_by_username(cls, username: str) -> dict:
        return cls._col().find_one({'username': username})

    @classmethod
    def find_by_id(cls, user_id: str) -> dict | None:
        try:
            return cls._col().find_one({'_id': ObjectId(user_id)}, {'password': 0})
        except Exception:
            return None

    @classmethod
    def create(cls, username: str, password: str, role: str = 'viewer',
               template_id: str = None) -> str:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        doc = {
            'username':   username,
            'password':   hashed.decode(),
            'role':       role,
            'created_at': datetime.utcnow(),
        }
        if template_id:
            doc['template_id'] = template_id
        result = cls._col().insert_one(doc)
        return str(result.inserted_id)

    @classmethod
    def update(cls, user_id: str, password: str = None, role: str = None,
               template_id=_UNSET) -> bool:
        """
        template_id=_UNSET  → 不動 template
        template_id='<id>'  → 指派模板
        template_id='' / None → 清除模板
        """
        set_fields   = {}
        unset_fields = {}

        if password:
            set_fields['password'] = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt()).decode()
        if role:
            set_fields['role'] = role

        if template_id is not _UNSET:
            if template_id:
                set_fields['template_id'] = template_id
            else:
                unset_fields['template_id'] = ''

        if not set_fields and not unset_fields:
            return False

        op = {}
        if set_fields:   op['$set']   = set_fields
        if unset_fields: op['$unset'] = unset_fields

        result = cls._col().update_one({'_id': ObjectId(user_id)}, op)
        return result.matched_count > 0

    @classmethod
    def delete(cls, user_id: str) -> str:
        """
        回傳值：
          'ok'        — 刪除成功
          'protected' — 系統保護帳號，不可刪除
          'not_found' — 找不到
        """
        try:
            doc = cls._col().find_one({'_id': ObjectId(user_id)}, {'username': 1})
        except Exception:
            return 'not_found'
        if not doc:
            return 'not_found'
        if doc.get('username') == 'admin':
            return 'protected'
        result = cls._col().delete_one({'_id': ObjectId(user_id)})
        return 'ok' if result.deleted_count > 0 else 'not_found'

    @classmethod
    def update_role_by_template(cls, template_id: str, role: str) -> int:
        """將所有指派此模板的使用者角色同步為 role，回傳更新筆數"""
        result = cls._col().update_many(
            {'template_id': str(template_id)},
            {'$set': {'role': role}}
        )
        return result.modified_count

    @staticmethod
    def check_password(plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
