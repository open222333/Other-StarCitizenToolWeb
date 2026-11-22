"""本地開發用：建立新聞測試資料，方便看玩家頁「新聞」分頁、「我的」上方公告與後台「新聞」頁。

⚠️ 只給本地／測試環境用，不要在正式環境跑（測試新聞會出現在所有人的新聞分頁）。

用法（在專案根目錄；api 容器沒有掛 scripts/，所以用標準輸入把檔案餵進去）：
    docker compose exec -T api python - < scripts/seed_demo_news.py              # 建立 1 則
    docker compose exec -T api python - --many < scripts/seed_demo_news.py       # 建立全部 14 則（看頭條、卡片、標籤顏色）
    docker compose exec -T api python - --remove < scripts/seed_demo_news.py     # 清掉測試新聞

測試資料怎麼認：標籤有「測試資料」、來源連結是 https://example.com/test-news/…。
重跑不會重複（同一個來源連結＝更新）；清除時直接刪掉（是測試資料，不走軟刪除）。
"""

import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/app')

from src.models import news  # noqa: E402
from src.mongo import get_db  # noqa: E402

TAG = '測試資料'
BY = 'seed'
BODY = """## 這是一則測試新聞

用來確認 **新聞版面** 顯示正常：

- 標題、封面、標籤、發布時間
- Markdown：**粗體**、*斜體*、`程式碼`、清單
- [RSI 官方網站](https://robertsspaceindustries.com)

> 測試完可以用 `--remove` 清掉。
"""
ITEMS = [
    # 「測試資料」標籤放最後：卡片只顯示前兩個標籤，放前面每張卡都只看到它
    {'title': '【測試】Alpha 4.x 改版重點整理', 'tags': ['改版', '官方', TAG], 'pinned': True,
     'cover_url': 'https://picsum.photos/seed/sctw1/1200/700'},
    {'title': '【測試】公會週末採礦團（週六晚上 9 點）', 'tags': ['公會活動', '採礦', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw2/800/500'},
    {'title': '【測試】RSI Comm-Link：新船預告', 'tags': ['RSI', '新船', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw3/800/500'},
    {'title': '【測試】伺服器維護公告', 'tags': ['公告', TAG]},
    {'title': '【測試】IAE 艦展開跑', 'tags': ['活動', 'IAE', '免費飛行週', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw5/800/500'},
    {'title': '【測試】貨運合約獎勵調整', 'tags': ['改版', '貨運', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw6/800/500'},
    {'title': '【測試】Nyx 星系首度開放：Levski 回歸，跳躍點路線與補給站一次看（標題很長看換行與截斷）',
     'tags': ['Nyx', 'PTU', '版本更新', TAG], 'cover_url': 'https://picsum.photos/seed/sctw7/800/500'},
    {'title': '【測試】Drake 新船外流（未證實）', 'tags': ['Drake', '未證實', '資料挖掘', TAG]},
    {'title': '【測試】Anvil Liberator 宣傳片', 'tags': ['Anvil', 'Liberator', '新船', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw9/800/500'},
    {'title': '【測試】Twitch 掉寶活動開跑', 'tags': ['Twitch掉寶', '活動', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw10/800/500'},
    {'title': '【測試】季度路線圖：工業玩法進度', 'tags': ['路線圖', '工業', '開發進度', TAG]},
    {'title': '【測試】商店限量船艦販售', 'tags': ['商店', '限量', '募資', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw12/800/500'},
    {'title': '【測試】社群創作精選', 'tags': ['社群', TAG],
     'cover_url': 'https://picsum.photos/seed/sctw13/800/500'},
    {'title': '【測試】封面網址失效（應顯示替代底圖）', 'tags': ['公告', TAG],
     'cover_url': 'https://example.invalid/broken.jpg'},
]


def seed(count: int):
    now = datetime.utcnow()
    batch = []
    for i, it in enumerate(ITEMS[:count]):
        batch.append({**it, 'body': BODY, 'source_url': f'https://example.com/test-news/{i + 1}',
                      'published_at': (now - timedelta(hours=i * 7)).isoformat() + 'Z'})
    result = news.ingest(batch, by=BY)
    print(f'新增 {len(result["created"])} 則、更新 {len(result["updated"])} 則測試新聞')


def remove():
    n = get_db()[news.COLLECTION].delete_many({'tags': TAG}).deleted_count
    print(f'刪除 {n} 則測試新聞')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--many', action='store_true', help='建立全部測試新聞（預設 1 則）')
    ap.add_argument('--remove', action='store_true', help='清掉測試新聞')
    args = ap.parse_args()
    if args.remove:
        remove()
    else:
        seed(len(ITEMS) if args.many else 1)
