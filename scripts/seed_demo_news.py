"""本地開發用：建立新聞測試資料，方便看玩家頁「新聞」分頁、「我的」上方公告與後台「新聞」頁。

⚠️ 只給本地／測試環境用，不要在正式環境跑（測試新聞會出現在所有人的新聞分頁）。

用法（在專案根目錄；api 容器沒有掛 scripts/，所以用標準輸入把檔案餵進去）：
    docker compose exec -T api python - < scripts/seed_demo_news.py              # 建立 1 則
    docker compose exec -T api python - --many < scripts/seed_demo_news.py       # 建立 6 則（看頭條版面）
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
    {'title': '【測試】Alpha 4.x 改版重點整理', 'tags': [TAG, '改版'], 'pinned': True,
     'cover_url': 'https://picsum.photos/seed/sctw1/1200/700'},
    {'title': '【測試】公會週末採礦團（週六晚上 9 點）', 'tags': [TAG, '公會活動'],
     'cover_url': 'https://picsum.photos/seed/sctw2/800/500'},
    {'title': '【測試】RSI Comm-Link：新船預告', 'tags': [TAG, 'RSI'],
     'cover_url': 'https://picsum.photos/seed/sctw3/800/500'},
    {'title': '【測試】伺服器維護公告', 'tags': [TAG, '公告']},
    {'title': '【測試】IAE 艦展開跑', 'tags': [TAG, '活動'],
     'cover_url': 'https://picsum.photos/seed/sctw5/800/500'},
    {'title': '【測試】貨運合約獎勵調整', 'tags': [TAG, '改版'],
     'cover_url': 'https://picsum.photos/seed/sctw6/800/500'},
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
    ap.add_argument('--many', action='store_true', help='建立 6 則（預設 1 則）')
    ap.add_argument('--remove', action='store_true', help='清掉測試新聞')
    args = ap.parse_args()
    if args.remove:
        remove()
    else:
        seed(len(ITEMS) if args.many else 1)
