"""「只留最新一份」的模組層快取，以同步項目最後的 run_id 當版本（G1：原本 ccu.py、loadout.py 各抄一份）。

用法：
    _cache = LatestCache(_build_rows)
    def rows():
        return _cache.get(run_ids('loadout', 'vehicles'))

- 版本字串（key）一樣就回上次的結果，不一樣才重算；只留最新一份，舊版本不會累積。
- 同步紀錄全空（測試、剛裝好還沒同步過）不快取，每次都重算。
- 一律回淺複本（list／dict），呼叫端改回傳值不會改到快取本體。

Unofficial Star Citizen fan tool. Not affiliated with the Cloud Imperium group of companies.
"""
from typing import Callable

from src.mongo import get_db


def run_ids(*job_ids: str) -> str:
    """幾個同步項目最後的 run_id 照順序用 | 串起來（沒同步過的是空字串），也拿來當 ETag。"""
    runs = {d['_id']: d.get('last_run_id') or '' for d in get_db()['sync_jobs'].find(
        {'_id': {'$in': list(job_ids)}}, {'last_run_id': 1})}
    return '|'.join(str(runs.get(k, '')) for k in job_ids)


def _blank(key) -> bool:
    parts = key if isinstance(key, (tuple, list)) else (key,)
    return not any(str(p or '').strip('|') for p in parts)


def _copy(rows):
    return list(rows) if isinstance(rows, list) else dict(rows) if isinstance(rows, dict) else rows


class LatestCache:
    def __init__(self, loader: Callable):
        self._loader = loader
        self.key = None
        self.rows = None

    def get(self, key, *, cache_blank: bool = False):
        """key 跟上次一樣回快取（淺複本），否則重算。key 全空時不快取，除非 cache_blank=True。"""
        if self.rows is not None and self.key == key:
            return _copy(self.rows)
        rows = self._loader()
        if cache_blank or not _blank(key):
            self.key, self.rows = key, rows
        return _copy(rows)

    def clear(self) -> None:
        self.key = self.rows = None
