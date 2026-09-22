"""英文 → 繁體中文物品/地點/礦物名稱對照。

資料來源：cosmo-chang-1701/sc-translation-pack（社群維護的星際公民繁中化包）
https://github.com/cosmo-chang-1701/sc-translation-pack/releases/tag/v4.10.1-rev.2

對照表是從該專案發布的 global.ini 萃取出來的，總共四份表、三種 key pattern：

  - 物品（sc_item_names_zh.json）：Item_Name_xxx=English Name\\n中文名稱，約 4,700 筆
    （目前還是舊版 v4.9.0-v49 萃取的，還沒跟礦物表一起升到 v4.10.1-rev.2）。
  - 地點（sc_location_names_zh.json）：StantonN[字母][_Xxx]=中文（English），
    涵蓋 Stanton／Pyro／Nyx 三個星系的星球、衛星、降落點、太空站、Lagrange
    點——2026-09 這次為了礦物回波的「地點」需求，把原本只抓
    StantonN_Xxx（一定要有底線後綴）的規則放寬成同時抓
    StantonN/PyroN/NyxN（裸的星球/衛星本身），新增 39 筆，現在共 77 筆。
    少數地點翻譯包完全沒有對應資料（多半是程序生成的採礦事件/資源點，例如
    "Resource Rush Gold"、"Lagrange (Occupied)"、"Ship Graveyard"、代號類
    的 "RMB-DARI"），查不到就顯示英文，不強行猜。
  - 礦物商品（sc_mining_resource_names_zh.json）：items_commodities_<slug>=
    English Name\\n中文名稱。這份以前誤以為官方翻譯包沒收錄礦物商品名稱，
    整份手工亂猜——後來查證發現翻譯包其實有這個獨立的 key namespace
    （跟物品表用的 Item_Name_xxx 不同命名空間，才會誤判翻譯包沒有）。
    39 個真正會用到的 mineable resource_key，38 個能在 items_commodities_*
    裡找到官方社群翻譯（含去掉 (Ore)/(Raw)/(Pure)/(R) 後綴、或去掉 "Raw "
    前綴的正規化比對——RawOuratite、RawSilicon 一開始就是漏在只做「去尾綴」
    沒做「去前綴」正規化，才會誤判翻譯包沒有這兩筆）；只剩 Raw_Ice 翻譯包
    真的沒收錄，保留人工最佳猜測（其實就是「冰」，沒什麼好猜的）。
    （Vlk_Limpet 這個 resource_key 對應的上游英文名稱本身就是垃圾資料
    '<= PLACEHOLDER =>'，沒有意義可翻，故意不收進這份表。）
  - 礦床名稱（sc_mining_deposit_names_zh.json，新增）：礦床的 DepositName
    （例如 "Granite Deposit"、"Aluminum (Ore)"）跟礦物商品名稱其實常常是
    同一個字串（單一礦物的礦床直接用該礦物當礦床名），所以大多數（38/56）
    直接重用礦物商品表的翻譯；少數通用岩石/小行星分類名稱
    （Granite/Gneiss/Obsidian/Quartzite/Shale/Felsic/Igneous/Atacamite
    Deposit、C~S 七種小行星光譜分類）翻譯包沒收錄，這些是有公認中文譯名的
    真實地質/天文學術語（不是猜測），直接用標準譯名；"Abandon"、
    "Calcified Coolant" 這兩個 DepositName 對應的都是開發用的佔位/測試
    礦床（Name 本身就是 '<= PLACEHOLDER =>'），故意不收進表。

只做「英文名稱 → 中文」的靜態查表，不會自動跟著遊戲改版更新——
game 改版後如果要更新，重新下載新版翻譯包，用同樣的規則重新萃取、覆蓋這幾個
JSON 檔即可（萃取腳本邏輯見對話紀錄，之後可以另外寫成 tasks/ 底下的維護腳本）。

四份表都是各自獨立的靜態 JSON 快取，_load_cached() 用檔案 mtime 判斷要不要
重讀——只改 JSON 檔不用重啟 worker/api container 就會生效，但同步進 DB 的
mining_deposit_master/mining_location_master 欄位仍是同步當下的快照，
改完 JSON 檔還是要重新跑一次同步才會反映到既有資料上。
"""

import json
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).resolve().parent / 'data'

# filename -> (mtime, data)。用 mtime 判斷要不要重讀，而不是「process 生命週期
# 只讀一次」——這幾份表都是人工維護、常常改完就直接覆蓋 JSON 檔，過去因為
# 讀了一次就永遠快取住，改完表卻要記得重啟 worker/api container 才會生效，
# 忘記重啟就會讓人誤以為「明明改了怎麼沒用」（實際發生過一次，見
# mining 對照表改用翻譯包來源那次）。這幾份表資料量都很小（最大的物品表
# 也才 4,700 筆），每次呼叫多一次 stat() 的成本可忽略不計。
_cache: dict = {}


def _load_cached(filename: str) -> dict:
    path = _DATA_DIR / filename
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _cache.pop(filename, None)
        return {}

    cached = _cache.get(filename)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    _cache[filename] = (mtime, data)
    return data


def item_name_zh(en_name: str) -> Optional[str]:
    """物品英文名稱 → 中文名稱，查不到回傳 None。"""
    return _load_cached('sc_item_names_zh.json').get((en_name or '').strip())


def location_name_zh(en_name: str) -> Optional[str]:
    """地點英文名稱 → 中文名稱，查不到回傳 None。"""
    return _load_cached('sc_location_names_zh.json').get((en_name or '').strip())


def mining_resource_name_zh(resource_key: str) -> Optional[str]:
    """礦物回波用的礦石/原礦 key（例如 'Ore_Aluminum'、'Raw_Quantainium'）→ 中文名稱。

    查不到回傳 None——查詢端（src/scdata.py 的 map_mining_deposit）遇到 None
    就只顯示英文名，不會讓整個同步或頁面掛掉。
    """
    return _load_cached('sc_mining_resource_names_zh.json').get((resource_key or '').strip())


def mining_deposit_name_zh(deposit_name: str) -> Optional[str]:
    """礦床名稱（例如 'Granite Deposit'、'Aluminum (Ore)'）→ 中文名稱。

    查不到回傳 None，行為跟 mining_resource_name_zh() 一致。
    """
    return _load_cached('sc_mining_deposit_names_zh.json').get((deposit_name or '').strip())
