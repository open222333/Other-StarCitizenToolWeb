"""英文 → 繁體中文物品/地點名稱對照。

資料來源：cosmo-chang-1701/sc-translation-pack（社群維護的星際公民繁中化包）
https://github.com/cosmo-chang-1701/sc-translation-pack/releases/tag/v4.9.0-v49

對照表是從該專案發布的 `global.ini` 萃取出來的：
  - 物品：`Item_Name_xxx=English Name\\n中文名稱` 這種 key，抓 4.9 版約 4,700 筆
  - 地點：`StantonN_Xxx=中文（English）` 這種 key，抓 Stanton 星系的降落點/前哨站約 38 筆

只做「英文名稱 → 中文」的靜態查表，不會自動跟著遊戲改版更新——
game 改版後如果要更新，重新下載新版翻譯包，用同樣的規則重新萃取、覆蓋這兩個 JSON 檔即可
（萃取腳本邏輯見這次對話紀錄，之後可以另外寫成 tasks/ 底下的維護腳本）。
"""

import json
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).resolve().parent / 'data'

_item_names: Optional[dict] = None
_location_names: Optional[dict] = None


def _load(filename: str) -> dict:
    path = _DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def item_name_zh(en_name: str) -> Optional[str]:
    """物品英文名稱 → 中文名稱，查不到回傳 None。"""
    global _item_names
    if _item_names is None:
        _item_names = _load('sc_item_names_zh.json')
    return _item_names.get((en_name or '').strip())


def location_name_zh(en_name: str) -> Optional[str]:
    """地點英文名稱 → 中文名稱，查不到回傳 None。"""
    global _location_names
    if _location_names is None:
        _location_names = _load('sc_location_names_zh.json')
    return _location_names.get((en_name or '').strip())
