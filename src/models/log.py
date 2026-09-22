"""後台操作稽核紀錄。

username 不是固定的列舉 —— 除了真的登入的後台帳號，還會出現兩種特殊值：
`unknown`（登入失敗、帳號欄位是空的）與 `player:<遊戲ID>`（玩家自助動作，
例如產生 Discord 綁定碼、批量登記藍圖，見 app/player/view.py）。所以「操作者」
下拉選單的選項要從 logs 自己的資料 distinct 出來（見 distinct_usernames），
不能借用 User.find_all() —— 那份清單只有註冊過的後台帳號，會漏掉上面兩種值。
"""

from datetime import datetime
from typing import Optional

from src.mongo import get_db

# 排序白名單 —— 目前只有「時間」這一欄有排序 UI，但用白名單而不是直接把
# 呼叫端傳進來的欄位名塞進 .sort()，是為了避免之後隨便加一個排序按鈕就
# 意外變成可以排序到任意欄位（雖然這裡不是使用者輸入，風險低，但保持一致）。
SORTABLE_FIELDS = {'created_at'}


class Log:
    COLLECTION = 'logs'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def create(cls, username: str, action: str, detail: str = '', success: bool = True) -> str:
        result = cls._col().insert_one({
            'username': username,
            'action': action,
            'detail': detail,
            'success': success,
            'created_at': datetime.utcnow()
        })
        return str(result.inserted_id)

    @classmethod
    def _build_query(cls, usernames=None, actions=None, success: Optional[bool] = None,
                      since: Optional[datetime] = None, until: Optional[datetime] = None) -> dict:
        query: dict = {}
        if usernames:
            query['username'] = {'$in': list(usernames)}
        if actions:
            query['action'] = {'$in': list(actions)}
        if success is not None:
            query['success'] = success
        if since is not None or until is not None:
            rng: dict = {}
            if since is not None:
                rng['$gte'] = since
            if until is not None:
                rng['$lte'] = until
            query['created_at'] = rng
        return query

    @classmethod
    def find_all(cls, limit: int = 200, offset: int = 0,
                 usernames=None, actions=None, success: Optional[bool] = None,
                 since: Optional[datetime] = None, until: Optional[datetime] = None,
                 sort_by: str = 'created_at', sort_dir: int = -1) -> list:
        """usernames／actions 是多選（列表），success 是「成功／失敗」單一布林
        （前端兩個都勾或都不勾＝不篩，轉換成 None 由呼叫端負責，見
        app/log/view.py 的 _success_filter）。
        """
        query = cls._build_query(usernames, actions, success, since, until)
        field = sort_by if sort_by in SORTABLE_FIELDS else 'created_at'
        direction = 1 if sort_dir == 1 else -1
        logs = (cls._col().find(query, {'_id': 0})
                .sort(field, direction).skip(offset).limit(limit))
        return list(logs)

    @classmethod
    def count(cls, usernames=None, actions=None, success: Optional[bool] = None,
              since: Optional[datetime] = None, until: Optional[datetime] = None) -> int:
        query = cls._build_query(usernames, actions, success, since, until)
        return cls._col().count_documents(query)

    @classmethod
    def distinct_usernames(cls) -> list:
        """給「操作者」篩選多選用。見檔頭說明，不能用 User.find_all() 代替。"""
        values = cls._col().distinct('username')
        return sorted(v for v in values if v)

    @classmethod
    def distinct_actions(cls) -> list:
        """給「動作」篩選多選用。從實際資料 distinct，不是手動維護的列舉 ——
        新增一種 action 字串不需要記得同步更新這裡。
        """
        values = cls._col().distinct('action')
        return sorted(v for v in values if v)
