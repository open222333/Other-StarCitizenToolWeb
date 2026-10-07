"""礦物回波參考表的唯讀模型（礦床成分機率 / 地點機率）。

資料來源：StarCitizenWiki/scunpacked-data（GitHub 上的解包資料集），由
tasks/scdata_sync.py 同步進 mining_deposit_master / mining_location_master
這兩個 collection，本模組只讀不寫。

⚠️ 這是**靜態**的成分/機率參考表——某種礦床可能含哪些礦物、比例區間、機率，
在哪個星系/地點出現——不是玩家實際掃描一顆礦石時看到的即時「回波」數值。
後者是遊戲端當下隨機生成的，沒有外部資料源，本模組與對應的前端頁面都
不記錄、也不嘗試預測它。

資料量小（目前約 270 個礦床、60 個地點群組），不特別做分頁/後端搜尋——
一次撈全部給前端做關鍵字篩選＋排序，比照使用者模板頁（UsersView）的作法。
"""

from typing import Optional

from src.mongo import get_db
from src.models import visibility
from src.models.uex_commodity import UexCommodity
from src.models.visibility import add_filter as add_visibility_filter


class MiningDeposit:
    """礦床成分機率表（scunpacked-data resources.json，Kind == 'mineable'）。"""

    COLLECTION = 'mining_deposit_master'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def list_all(cls, visible_only: bool = False) -> list:
        """全部現行礦床（含成分機率明細），依名稱排序。不含 raw 原始資料。

        visible_only（玩家端）：不列玩家頁面不顯示的礦床，成分裡也拿掉不顯示的礦物
        （見 src/models/visibility.py）。
        """
        rows = list(cls._col().find(
            add_visibility_filter({'is_current': True}, visible_only=visible_only), {'raw': 0},
        ).sort('deposit_name_lower', 1))
        if visible_only:
            hidden = {k for k, v in visibility.minerals_state(rows).items() if not v['player_visible']}
            if hidden:
                for row in rows:
                    row['parts'] = [p for p in row.get('parts') or [] if p.get('resource_key') not in hidden]
        # 每個礦物補上 UEX 商品縮寫（例如 QUAN），關聯規則見 src/models/uex_commodity.py
        names = {p['resource_key']: p.get('resource_name') for row in rows
                 for p in row.get('parts') or [] if p.get('resource_key')}
        links = UexCommodity.links_for(names)
        for row in rows:
            for part in row.get('parts') or []:
                part['uex'] = links.get(part.get('resource_key'))
        return rows

    @classmethod
    def get(cls, doc_id: str) -> Optional[dict]:
        """按 uuid 取單筆（含 raw）。不過濾 is_current。"""
        return cls._col().find_one({'_id': doc_id})

    @classmethod
    def by_ids(cls, doc_ids) -> dict:
        """一次查多個礦床 uuid 的摘要，回傳 `{uuid: {'deposit_name':…, 'tier':…}}`。

        給 MiningLocation.list_all() 把 Groups[].Deposits[].resource_uuid
        展開成礦床名稱用——批次 `$in` 一次查完，不逐筆 find_one。
        """
        ids = [i for i in {str(i) for i in doc_ids if i} if i]
        if not ids:
            return {}
        rows = cls._col().find(
            {'_id': {'$in': ids}}, {'deposit_name': 1, 'tier': 1},
        )
        return {r['_id']: {'deposit_name': r.get('deposit_name'), 'tier': r.get('tier')}
                for r in rows}

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})


class MiningLocation:
    """星系/地點 -> 可能出現哪些礦床、機率多少（scunpacked-data locations.json）。"""

    COLLECTION = 'mining_location_master'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def list_all(cls, visible_only: bool = False) -> list:
        """全部現行地點（含各礦床出現機率），把 deposits 展開成礦床名稱＋Tier。

        visible_only（玩家端）：不列玩家頁面不顯示的地點，群組裡也拿掉不顯示的礦床。

        同步階段（src/scdata.py 的 map_mining_location）只存了 resource_uuid，
        查詢端才展開成名稱——資料量小（幾十個地點、至多幾百個礦床參照），
        用 MiningDeposit.by_ids() 批次查一次在 Python 端組 map 就夠了，
        不需要 Mongo $lookup 展開巢狀陣列那套複雜度。
        """
        rows = list(cls._col().find(
            add_visibility_filter({'is_current': True}, visible_only=visible_only), {'raw': 0},
        ).sort('location_name_lower', 1))

        all_uuids = set()
        for row in rows:
            for group in row.get('groups', []):
                for dep in group.get('deposits', []):
                    if dep.get('resource_uuid'):
                        all_uuids.add(dep['resource_uuid'])
        deposit_info = MiningDeposit.by_ids(all_uuids)
        hidden_deposits = set()
        if visible_only and all_uuids:
            hidden_deposits = {r['_id'] for r in MiningDeposit._col().find(
                {'_id': {'$in': list(all_uuids)}, 'player_visible': False}, {'_id': 1})}

        for row in rows:
            for group in row.get('groups', []):
                for dep in group.get('deposits', []):
                    info = deposit_info.get(dep.get('resource_uuid')) or {}
                    dep['deposit_name'] = info.get('deposit_name')
                    dep['tier'] = info.get('tier')
                if visible_only:
                    group['deposits'] = [
                        d for d in group.get('deposits', [])
                        if d.get('resource_uuid') not in hidden_deposits]
            if visible_only:
                row['groups'] = [g for g in row.get('groups', []) if g.get('deposits')]
        return rows

    @classmethod
    def systems(cls) -> list:
        """所有出現過的星系名稱，給篩選下拉選單用。"""
        return sorted(s for s in cls._col().distinct('system', {'is_current': True}) if s)

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})
