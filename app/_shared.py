"""兩個以上 blueprint 共用的小工具。

目前只放 `attach_item_names()` —— 它原本在 `app/inventory/view.py` 與
`app/player/view.py` 各寫了一份逐筆 `ItemMaster.get()` 的迴圈，而且兩份
**已經開始漂移**：player 版會補 `item_name_zh`，inventory 版沒有，於是
同一種「異動紀錄」在兩支 API 回傳的形狀不一樣，前端得各寫一套處理。

集中在這裡的另一個好處是批次查詢只實作一次（見
`ItemMaster.names_by_ids()`）—— 逐筆版本一頁最多會打 200 次 find_one。
"""

from src.models.item import ItemMaster


def attach_item_names(rows, id_field: str = 'item_id') -> list:
    """就地補上 `item_name` / `item_name_zh`，回傳同一個 list。

    名稱查不到（主檔還沒同步、或物品已從 API 消失）時 `item_name` 退回
    uuid 本身 —— 前端至少有東西可顯示，不會出現空白列。

    兩支 /history 端點都用這支，所以回傳形狀一定一致：
    `item_name` 一律有值，`item_name_zh` 可能是 None。
    """
    rows = list(rows)
    names = ItemMaster.names_by_ids(row.get(id_field) for row in rows)
    for row in rows:
        item_id = row.get(id_field)
        info = names.get(item_id) or {}
        row['item_name'] = info.get('name') or item_id
        row['item_name_zh'] = info.get('name_zh')
    return rows
