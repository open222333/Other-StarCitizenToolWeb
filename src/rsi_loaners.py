"""RSI 官方「借用船清單」（Loaner Ship Matrix）：抓取與解析（寫入見 src/models/ship_loaner.py）。

買了還沒做進遊戲（概念、製作中）的船，RSI 會先借別的船給你飛，清單在官方客服知識庫的一篇文章：
https://support.robertsspaceindustries.com/hc/en-us/articles/360003093114-Loaner-Ship-Matrix
用 Zendesk 的公開 API 取文章（不用登入），內文是一張兩欄表：YOUR SHIP ／ OUR LOANER(S)。

⚠️ 左欄是人寫的說明文字，不是商店船名，有這些寫法（parse_ship_names 會展開）：
  「600i Explorer and Executive」「Hull D, E」「Idris-M & P」「Carrack / Carrack Expedition」
  「Fury Variants」（＝Fury 開頭的全部）「Pulse (+ LX)」「X1 (+ Velocity, Force)」
右欄用逗號分開，「Polaris, Ironclad Assault, Buccaneer」。
"""

import re
from html.parser import HTMLParser
from typing import Optional

ARTICLE_ID = '360003093114'
ARTICLE_API = f'https://support.robertsspaceindustries.com/api/v2/help_center/en-us/articles/{ARTICLE_ID}.json'
ARTICLE_URL = f'https://support.robertsspaceindustries.com/hc/en-us/articles/{ARTICLE_ID}-Loaner-Ship-Matrix'
#: 抓到的列數少於這個就當作格式變了，不更新
MIN_ROWS = 10


class LoanerError(Exception):
    pass


class _TableParser(HTMLParser):
    """抓第一張表的每一列（每格的純文字）。"""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._depth, self._done = [], None, None, 0, False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if tag == 'table':
            self._depth += 1
        elif tag == 'tr' and self._depth:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
        elif tag == 'br' and self._cell is not None:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if self._done:
            return
        if tag in ('td', 'th') and self._cell is not None:
            self._row.append(' '.join(''.join(self._cell).split()))
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
        elif tag == 'table':
            self._depth -= 1
            self._done = self._depth == 0

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_matrix(html: str) -> list:
    """文章 HTML → [{ship: 左欄原文, loaners: [借用船…]}]（跳過表頭）。"""
    p = _TableParser()
    p.feed(html or '')
    out = []
    for row in p.rows:
        if len(row) < 2:
            continue
        ship, loaners = row[0].strip(), row[1].strip()
        if not ship or ship.upper().startswith('YOUR SHIP'):
            continue
        names = [n.strip() for n in re.split(r'\s*,\s*', loaners) if n.strip()]
        out.append({'ship': ship, 'loaners': names})
    return out


def _norm(text) -> str:
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', str(text or '').lower()).split())


def _swap_last(left: str, right: str) -> str:
    """「Hull D」＋「E」→「Hull E」；「Idris-M」＋「P」→「Idris-P」；「600i Explorer」＋「Executive」→「600i Executive」。"""
    m = re.match(r'^(.*[\s-])[^\s-]+$', left)
    return f'{m.group(1)}{right}' if m else right


def parse_ship_names(text: str) -> list:
    """左欄 → [(名稱, 是否為字首比對)]。名稱是原本的大小寫，比對時再正規化。"""
    out = []
    for part in re.split(r'\s+/\s+', text or ''):
        part = part.strip()
        if not part:
            continue
        # 「X1 (+ Velocity, Force)」「Pulse (+ LX)」
        m = re.match(r'^(.*?)\s*\(\+\s*([^)]*)\)\s*$', part)
        if m:
            base = m.group(1).strip()
            out.append((base, False))
            out += [(f'{base} {x.strip()}', False) for x in m.group(2).split(',') if x.strip()]
            continue
        # 「Fury Variants」
        m = re.match(r'^(.*?)\s+variants?$', part, re.I)
        if m:
            out.append((m.group(1).strip(), True))
            continue
        # 「Hull D, E」「Idris-M & P」「600i Explorer and Executive」
        pieces = [x.strip() for x in re.split(r'\s*(?:,|&|\band\b)\s*', part) if x.strip()]
        if len(pieces) > 1:
            first = pieces[0]
            out.append((first, False))
            out += [(_swap_last(first, x) if len(x.split()) == 1 else x, False) for x in pieces[1:]]
            continue
        out.append((part, False))
    return out


def match_row(ship_name: str, rows: list, manufacturer: str = '') -> Optional[dict]:
    """商店船名 → 清單裡對應的那一列；先找名稱完全相同（忽略大小寫、標點；可帶或不帶廠商），再找字首（Variants）。"""
    n = _norm(ship_name)
    if not n:
        return None
    cands = {n}
    m = _norm(manufacturer)
    if m and n.startswith(m + ' '):
        cands.add(n[len(m) + 1:])
    if m:
        first = m.split()[0]
        if n.startswith(first + ' '):
            cands.add(n[len(first) + 1:])
    prefix_hit = None
    for row in rows:
        for name, is_prefix in row.get('names') or parse_ship_names(row['ship']):
            k = _norm(name)
            if not k:
                continue
            if not is_prefix and k in cands:
                return row
            if is_prefix and prefix_hit is None and any(c == k or c.startswith(k + ' ') for c in cands):
                prefix_hit = row
    return prefix_hit


def fetch_matrix(client) -> dict:
    """抓文章 → {rows, updated_at（文章最後更新，ISO）, url}；格式不對丟 LoanerError。"""
    try:
        resp = client.get(ARTICLE_API)
    except Exception as err:  # 連線錯誤、逾時
        raise LoanerError(f'連不到 RSI 客服知識庫：{err}') from err
    if resp.status_code != 200:
        raise LoanerError(f'RSI 客服知識庫回 HTTP {resp.status_code}')
    try:
        article = (resp.json() or {}).get('article') or {}
    except ValueError as err:
        raise LoanerError('RSI 客服知識庫回的不是 JSON') from err
    rows = parse_matrix(article.get('body') or '')
    if len(rows) < MIN_ROWS:
        raise LoanerError(f'借用船清單只解析出 {len(rows)} 列（少於 {MIN_ROWS}），可能文章格式改了，不更新')
    return {'rows': rows, 'updated_at': article.get('updated_at'), 'url': article.get('html_url') or ARTICLE_URL}
