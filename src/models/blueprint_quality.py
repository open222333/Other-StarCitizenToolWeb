"""藍圖「品質試算」資料（`blueprint_quality_master`，來源 scunpacked-data blueprints.json，
由「藍圖」同步項目寫入，見 src/scdata.py 的 map_blueprint_quality）。

每張藍圖分成幾個部位（Frame、Barrel…），每個部位放一種材料；材料品質 0–1000
線性影響該部位列出的屬性（modifiers：q_min／q_max 對應 at_min／at_max 倍率）。
試算本身在前端做（frontend/src/utils/craftQuality.js），這裡只補上中文。
"""

from typing import Optional

from src.mongo import get_db
from src.sc_zh import crafting_slot_zh, crafting_stat_zh, mining_resource_name_zh, item_name_zh

COLLECTION = 'blueprint_quality_master'


def get(blueprint_uuid: str) -> Optional[dict]:
    doc = get_db()[COLLECTION].find_one({'_id': str(blueprint_uuid or ''), 'is_current': {'$ne': False}},
                                        {'_sync': 0, 'first_seen_at': 0})
    if not doc:
        return None
    for slot in doc.get('slots') or []:
        slot['name_zh'] = crafting_slot_zh(slot.get('name') or '')
        for m in slot.get('modifiers') or []:
            m['name_zh'] = crafting_stat_zh(m.get('name') or '')
        for opt in slot.get('options') or []:
            name = opt.get('name') or ''
            opt['name_zh'] = (mining_resource_name_zh(name=name) if opt.get('kind') == 'resource'
                              else item_name_zh(name))
    return doc
