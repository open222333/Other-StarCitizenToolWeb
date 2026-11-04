"""合約分配（玩家頁「航線 › 合約分配」）：多份運貨合約 × 多個小隊，算出每隊載哪些貨、照什麼順序跑。

輸入：
  - 合約（最多 MAX_CONTRACTS 份），每份有幾項貨物：{貨物名稱, 取貨點 [{地點, SCU}], 送貨點 [{地點, SCU}]}。
    貨物只能送到「同一份合約」的送貨點（同名貨物、不同合約也不能互相繳交）；
    同一項貨物有好幾個取貨點、送貨點時，先依距離把有填 SCU 的取貨點配給送貨點（_pair，近的先配），
    變成幾組綁定的取貨→送貨。
    沒填 SCU 的取貨點（有些任務不會告知各點有多少，但每個點都有貨、至少要去一次）有兩個以上時不猜數量：
    合成一個「收集任務」——同一隊一趟依序去完這些取貨點（貨艙從第一個點起就預留剩下的全部量，不會超載），
    再送到還缺貨的送貨點；只有一個沒填的取貨點時數量就是剩下的量，照一般任務處理。
  - 小隊（最多 MAX_SQUADS 隊），各自的船、量子引擎、起點（不填＝共同起點）。

做法：
  1. 拆成「任務」：一項貨物比最大的貨艙還多時，平均拆成幾趟（每趟 ≤ 最大貨艙）；
     同一份合約的貨物可以分給不同小隊（遊戲裡要共享合約）。
     每個任務只能給貨艙裝得下、外掛貨櫃（只能停太空站）也停得了的小隊。
  2. 分配：先依 SCU 由大到小，逐一插進「插進去之後整體目標最好」的小隊、該隊航線裡最好的位置
     （取貨一定在送貨前、途中載貨量不超過貨艙）；再反覆把單一任務搬到別隊／同隊別的位置，
     有改善就接受，直到沒有改善或超過 SEARCH_SECONDS。
  3. 每隊最後再用 src/models/nav.py 的 _order（事件少時是精確的動態規劃）重排一次，取比較好的那個。
  4. 方案（OBJECTIVES）：最快完成（最晚完成的那隊越早越好）、總時間最少（各隊時間加總）、
     總油量最少（各隊耗油加總）。時間、油耗、補燃料、載重係數都跟一般航線同一套（nav.Planner）。
  5. 另外一個「站點平均」方案（STATIONS_KEY，_assign_stations）：每個站點（取貨點、送貨點都算）只給一隊去，
     各隊航程（距離）盡量一樣、其次總距離短。一筆貨的取、送站點一定同一隊，所以有貨物相連的站點綁成一組
     （_station_groups）一起分；組數比隊數少時有些隊會分不到。
"""

import math
import random
import time

from src.models import nav
from src.models.nav import RouteError

MAX_CONTRACTS = 10
MAX_ITEMS = 10
#: 每項貨物的取貨點／送貨點各最多幾個
MAX_POINTS = 30
MAX_SQUADS = 6
MAX_TASKS = 80
#: 每個方案的分配搜尋最多跑幾秒
SEARCH_SECONDS = 1.0

OBJECTIVES = (
    ('time', '最快完成'),
    ('total', '總時間最少'),
    ('fuel', '總油量最少'),
)
#: 方案 → 每隊航線用哪種成本（nav.Planner.leg_cost 的 plan）
_LEG_COST = {'time': 'fastest', 'total': 'fastest', 'fuel': 'fuel'}
SHIP_KEYS = ('id', 'name', 'name_zh', 'qt_speed', 'qt_spool', 'qt_fuel_capacity', 'qt_range', 'qt_fuel_per_m',
             'cargo_scu', 'mass_total', 'qd_uuid', 'qd_name', 'qd_size')


def _split(scu: float, parts: int) -> list:
    """平均拆成 parts 份；整數 SCU 拆成整數（前面幾份多 1）。"""
    if parts <= 1:
        return [scu]
    if float(scu).is_integer():
        base, extra = divmod(int(scu), parts)
        return [float(base + (1 if i < extra else 0)) for i in range(parts)]
    return [scu / parts] * parts


def _stops_of(task: dict, sign: int) -> list:
    """任務的取貨串（sign > 0）或送貨串 → [(地點, 載貨量變化)]。
    一般任務各一個點；收集任務（unknown）取貨是好幾個點、量不知道：第一個點就算進整趟的量（預留貨艙），其餘 0。"""
    if sign > 0:
        return [(n, task['scu'] if k == 0 else 0.0) for k, n in enumerate(task['pickups'])]
    return [(n, -amount) for n, amount in task['drops']]


def _chain(items: list, distance, node=lambda x: x, after=None) -> list:
    """一串點的拜訪順序（最近鄰；node 取出地點）：after 有給就從離它最近的開始，
    否則每個起點都試、取總距離最短的。"""
    if len(items) <= 1:
        return list(items)

    def walk(first):
        order, rest = [first], [i for i in range(len(items)) if i != first]
        while rest:
            nxt = min(rest, key=lambda i: distance(node(items[order[-1]]), node(items[i])))
            order.append(nxt)
            rest.remove(nxt)
        return [items[i] for i in order]

    def length(o):
        return sum(distance(node(a), node(b)) for a, b in zip(o, o[1:]))

    if after is not None:
        return walk(min(range(len(items)), key=lambda i: distance(after, node(items[i]))))
    return min((walk(i) for i in range(len(items))), key=length)


class _Squad:
    """一個小隊的航線成本計算（插入、整條重算），成本單位看方案：時間（秒）或油量。"""

    def __init__(self, info: dict, planner: nav.Planner, cost_key: str):
        self.info = info
        self.planner = planner
        self.cost_key = cost_key
        self.cap = info['cap']
        self.start = info['start']
        self.end = info['end']
        self._memo: dict = {}

    def leg(self, a: dict, b: dict, load: float) -> float:
        key = (a['id'], b['id'], round(load, 3))
        if key not in self._memo:
            self._memo[key] = self.planner.leg_cost(a, b, load, self.cost_key)
        return self._memo[key]

    def cost(self, seq: list) -> float:
        """seq：[(任務, +1 取貨／-1 送貨)]；超過貨艙回 inf。
        任務的取貨、送貨各是一串地點（_stops_of）：取貨在第一個點就加上整趟的量，送貨每個點扣各自的量。"""
        if not seq:
            return 0.0
        cur, load, total = self.start, 0.0, 0.0
        for task, sign in seq:
            for node, delta in _stops_of(task, sign):
                total += self.leg(cur, node, load)
                load += delta
                if load > self.cap + 1e-9:
                    return math.inf
                cur = node
        if self.end:
            total += self.leg(cur, self.end, load)
        return total

    def best_insert(self, seq: list, task: dict) -> tuple:
        """把任務插到 seq 裡最好的位置（取貨在送貨前、途中不超過貨艙）→ (成本, 新 seq)。

        挑位置時用空載的航段成本估「多繞的路」（O(n²)），挑好之後整條用實際載重重算一次。"""
        n, scu, cap = len(seq), task['scu'], self.cap
        # 每一段（取貨串／送貨串）的進入點、離開點；串內的路程是固定的
        enter, leave, loads, load = [], [], [], 0.0
        for t, sign in seq:
            chain = _stops_of(t, sign)
            enter.append(chain[0][0])
            leave.append(chain[-1][0])
            load += sign * t['scu']
            loads.append(load)

        def leg(a, b):
            return self.leg(a, b, 0.0) if a is not None and b is not None else 0.0

        def inner(chain):
            return sum(leg(a[0], b[0]) for a, b in zip(chain, chain[1:]))

        picks, drops = _stops_of(task, 1), _stops_of(task, -1)
        pick_in, pick_out, pick_len = picks[0][0], picks[-1][0], inner(picks)
        drop_in, drop_out, drop_len = drops[0][0], drops[-1][0], inner(drops)

        def around(i):
            return (self.start if i == 0 else leave[i - 1]), (enter[i] if i < n else self.end)

        best = (math.inf, None, None)
        for i in range(n + 1):
            if (loads[i - 1] if i else 0.0) + scu > cap + 1e-9:
                continue
            prev, nxt = around(i)
            base = leg(prev, nxt)
            c = leg(prev, pick_in) + pick_len + leg(pick_out, drop_in) + drop_len + leg(drop_out, nxt) - base
            if c < best[0]:
                best = (c, i, i)
            add_pick = leg(prev, pick_in) + pick_len + leg(pick_out, nxt) - base
            peak = -math.inf
            for j in range(i + 1, n + 1):
                peak = max(peak, loads[j - 1])
                if peak + scu > cap + 1e-9:
                    break
                pj, nj = around(j)
                c = add_pick + leg(pj, drop_in) + drop_len + leg(drop_out, nj) - leg(pj, nj)
                if c < best[0]:
                    best = (c, i, j)
        if best[1] is None:
            return math.inf, None
        _, i, j = best
        new = seq[:i] + [(task, 1)] + seq[i:j] + [(task, -1)] + seq[j:]
        return self.cost(new), new


#: 「站點平均」方案（見模組說明 5）
STATIONS_KEY = 'stations'
STATIONS_LABEL = '站點平均'


def _score(objective: str, costs: list) -> float:
    if objective in ('time', STATIONS_KEY):
        # 最晚完成的那隊；一樣的話總時間少的好
        return max(costs) + sum(costs) * 1e-6
    return sum(costs)


def _construct(tasks: list, squads: list, objective: str) -> tuple:
    """依 tasks 的順序逐一插到「插進去之後整體目標最好」的小隊 → (seqs, costs, owner)。"""
    seqs = [[] for _ in squads]
    costs = [0.0] * len(squads)
    owner = {}
    for task in tasks:
        best = None
        for si in task['eligible']:
            c, seq = squads[si].best_insert(seqs[si], task)
            if seq is None or c == math.inf:
                continue
            trial = costs[:]
            trial[si] = c
            score = _score(objective, trial)
            if best is None or score < best[0]:
                best = (score, si, c, seq)
        if best is None:
            raise RouteError(f'{task["contract_name"]} {task["item_name"]}：貨艙容量不足，排不出可行的分配')
        _, si, c, seq = best
        seqs[si], costs[si], owner[task['id']] = seq, c, si
    return seqs, costs, owner


def _without(seq: list, task: dict) -> list:
    return [e for e in seq if e[0] is not task]


def _improve(tasks: list, squads: list, objective: str, state: tuple, deadline: float) -> tuple:
    """局部搜尋：搬一個任務到別隊／同隊別的位置、兩隊互換一個任務，有改善就接受。"""
    seqs, costs, owner = state
    improved = True
    while improved and time.monotonic() < deadline:
        improved = False
        # 搬移
        for task in tasks:
            if time.monotonic() >= deadline:
                return seqs, costs, owner
            si = owner[task['id']]
            removed = _without(seqs[si], task)
            removed_cost = squads[si].cost(removed)
            current = _score(objective, costs)
            for sj in task['eligible']:
                c, seq = squads[sj].best_insert(removed if sj == si else seqs[sj], task)
                if seq is None or c == math.inf:
                    continue
                trial = costs[:]
                trial[si] = removed_cost
                trial[sj] = c
                if _score(objective, trial) < current - 1e-6:
                    if sj != si:
                        seqs[si] = removed
                    seqs[sj], costs, owner[task['id']] = seq, trial, sj
                    improved = True
                    break
        # 互換
        for a_i, a in enumerate(tasks):
            for b in tasks[a_i + 1:]:
                if time.monotonic() >= deadline:
                    return seqs, costs, owner
                sa, sb = owner[a['id']], owner[b['id']]
                if sa == sb or sb not in a['eligible'] or sa not in b['eligible']:
                    continue
                ca, seq_a = squads[sa].best_insert(_without(seqs[sa], a), b)
                cb, seq_b = squads[sb].best_insert(_without(seqs[sb], b), a)
                if seq_a is None or seq_b is None or math.inf in (ca, cb):
                    continue
                trial = costs[:]
                trial[sa], trial[sb] = ca, cb
                if _score(objective, trial) < _score(objective, costs) - 1e-6:
                    seqs[sa], seqs[sb], costs = seq_a, seq_b, trial
                    owner[a['id']], owner[b['id']] = sb, sa
                    improved = True
    return seqs, costs, owner


def _assign(tasks: list, squads: list, objective: str, deadline: float) -> list:
    """先照 SCU 由大到小建一個解並改良；時間還夠就打亂順序重建、改良，留最好的 → 每隊的 seq。"""
    rng = random.Random(0)
    order = sorted(tasks, key=lambda t: (-t['scu'], t['id']))
    best = None
    while True:
        state = _improve(tasks, squads, objective, _construct(order, squads, objective), deadline)
        score = _score(objective, state[1])
        if best is None or score < best[0] - 1e-9:
            best = (score, state)
        if time.monotonic() >= deadline or len(tasks) <= 1:
            break
        order = sorted(tasks, key=lambda t: -t['scu'] * rng.uniform(0.3, 1.0))
    return best[1][0]


def _station_ids(task: dict) -> list:
    return [n['id'] for n in task['pickups']] + [d['id'] for d, _ in task['drops']]


def _station_groups(tasks: list) -> list:
    """有貨物相連（取貨點→送貨點）的站點綁成一組 → [[任務]]，組跟組之間沒有共用的站點。"""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for t in tasks:
        ids = _station_ids(t)
        for other in ids[1:]:
            parent[find(other)] = find(ids[0])
    groups = {}
    for t in tasks:
        groups.setdefault(find(_station_ids(t)[0]), []).append(t)
    return list(groups.values())


def _assign_stations(groups: list, squads: list, deadline: float) -> list:
    """站點平均：每組站點整組給一隊（組內任務逐一插進那隊航線），各隊航程（squad 的成本用距離）的最大值越小越好、
    其次總和；先依組的任務數由多到少貪婪分配，再反覆搬一組到別隊、兩隊互換一組，有改善就接受 → 每隊的 seq。"""
    n = len(squads)

    def eligible(g, si):
        return all(si in t['eligible'] for t in g)

    def add(si, seq, g):
        """把一組任務插進 seq → (新 seq, 成本)；裝不下回 (None, inf)。"""
        for t in g:
            _, seq = squads[si].best_insert(seq, t)
            if seq is None:
                return None, math.inf
        return seq, squads[si].cost(seq)

    def remove(si, seq, g):
        ids = {t['id'] for t in g}
        seq = [e for e in seq if e[0]['id'] not in ids]
        return seq, squads[si].cost(seq)

    owned = [[] for _ in range(n)]
    seqs, costs = [[] for _ in range(n)], [0.0] * n
    for g in sorted(groups, key=lambda g: (-len(g), -sum(t['scu'] for t in g))):
        best = None
        for si in range(n):
            if not eligible(g, si):
                continue
            seq, c = add(si, seqs[si], g)
            if seq is None:
                continue
            trial = costs[:]
            trial[si] = c
            score = _score(STATIONS_KEY, trial)
            if best is None or score < best[0]:
                best = (score, si, seq, c)
        if best is None:
            t = g[0]
            raise RouteError(f'{t["contract_name"]} {t["item_name"]}：站點平均分配時沒有小隊載得了這組站點的貨')
        _, si, seq, c = best
        owned[si].append(g)
        seqs[si], costs[si] = seq, c

    def try_change(a, b, out_a, in_a, out_b, in_b):
        """a 隊拿掉 out_a、加 in_a；b 隊拿掉 out_b、加 in_b；整體變好就套用。"""
        seq_a, ca = remove(a, seqs[a], out_a)
        if in_a:
            seq_a, ca = add(a, seq_a, in_a)
        seq_b, cb = remove(b, seqs[b], out_b) if out_b else (seqs[b], costs[b])
        if in_b and seq_b is not None:
            seq_b, cb = add(b, seq_b, in_b)
        if seq_a is None or seq_b is None:
            return False
        trial = costs[:]
        trial[a], trial[b] = ca, cb
        if _score(STATIONS_KEY, trial) >= _score(STATIONS_KEY, costs) - 1e-6:
            return False
        seqs[a], seqs[b], costs[:] = seq_a, seq_b, trial
        return True

    improved = True
    while improved and time.monotonic() < deadline:
        improved = False
        # 搬移：a 隊的一組搬到 b 隊
        for a in range(n):
            for g in list(owned[a]):
                for b in range(n):
                    if time.monotonic() >= deadline:
                        return seqs
                    if b != a and eligible(g, b) and try_change(a, b, g, None, None, g):
                        owned[a].remove(g)
                        owned[b].append(g)
                        improved = True
                        break
        # 互換：a 隊的一組跟 b 隊的一組對調
        for a in range(n):
            for b in range(a + 1, n):
                for ga in list(owned[a]):
                    for gb in list(owned[b]):
                        if time.monotonic() >= deadline:
                            return seqs
                        if ga not in owned[a] or gb not in owned[b] or not eligible(ga, b) or not eligible(gb, a):
                            continue
                        if try_change(a, b, ga, gb, gb, ga):
                            owned[a].remove(ga)
                            owned[a].append(gb)
                            owned[b].remove(gb)
                            owned[b].append(ga)
                            improved = True
    return seqs


def _events_of(seq: list) -> list:
    """seq → nav 的事件（取貨／送貨，送貨要先取貨）。"""
    events, pick_index = [], {}
    for task, sign in seq:
        common = {'cargo': task['id'] + 1, 'contract': task['contract'],
                  'contract_name': task['contract_name'], 'item': task['item'], 'item_name': task['item_name'],
                  'item_named': task['item_named']}
        if sign > 0:
            # 收集任務：量不知道（scu None、scu_unknown），第一個點預留整趟的量；
            # 取貨點照順序（後一個要先去前一個，重排時預留的那個點一定最先到，貨艙不會算少）
            prev = None
            for node, delta in _stops_of(task, 1):
                events.append({'node': node, 'delta': delta, 'need': prev, 'kind': 'pickup', **common,
                               'scu': None if task['unknown'] else task['scu'],
                               **({'scu_unknown': True} if task['unknown'] else {})})
                prev = len(events) - 1
            pick_index[task['id']] = prev
        else:
            for node, delta in _stops_of(task, -1):
                events.append({'node': node, 'delta': delta, 'need': pick_index[task['id']],
                               'kind': 'dropoff', **common, 'scu': -delta})
    return events


def _polish(squad: _Squad, seq: list) -> list:
    """用 nav._order 再排一次（事件少時是精確解），比較好就換。"""
    if len(seq) <= 2:
        return seq
    events = _events_of(seq)
    # 有好幾個點的任務（收集任務）：事件跟 seq 不是一對一，重排結果對不回 seq，不重排
    if len(events) != len(seq):
        return seq
    # 事件太多時 nav._order 走近似排序（每次最多 HEURISTIC_SECONDS），三種方案 × 多隊會拖太久；分配搜尋已經排過
    if len(events) > nav.EXACT_LIMIT:
        return seq
    try:
        order = nav._order(squad.planner, squad.start, events, squad.end, squad.cost_key, True, squad.cap)
    except RouteError:
        return seq
    cand = [seq[i] for i in order]
    return cand if squad.cost(cand) < squad.cost(seq) - 1e-9 else seq


def _points(rows, label: str, node) -> list:
    """[{place, scu}] → [[節點, SCU 或 None]]（同一個地點合併）。"""
    if not isinstance(rows, list) or not rows:
        raise RouteError(f'{label}：請至少選一個地點')
    if len(rows) > MAX_POINTS:
        raise RouteError(f'{label}：地點最多 {MAX_POINTS} 個')
    out = {}
    for row in rows:
        row = row if isinstance(row, dict) else {}
        n = node(row.get('place'), label)
        raw = row.get('scu')
        if raw in (None, ''):
            scu = None
        else:
            try:
                scu = float(raw)
            except (TypeError, ValueError):
                raise RouteError(f'{label}：SCU 格式錯誤')
            if not 0 < scu < 1e6:
                raise RouteError(f'{label}：SCU 要大於 0')
        if n['id'] in out:
            prev = out[n['id']][1]
            out[n['id']][1] = None if prev is None or scu is None else prev + scu
        else:
            out[n['id']] = [n, scu]
    return list(out.values())


def _item_points(it: dict, label: str, node) -> tuple:
    """一項貨物的取貨點、送貨點（各自可以好幾個）→ (supply, demand)。

    送貨點的 SCU 要填（只有一個送貨點、取貨點都有填時可以不填，就是取貨合計）。
    取貨點不見得知道各拿多少：沒填的取貨點平均分掉剩下的量（每個取貨點都一定要去，見 _pair）；
    有填的就一定要拿完。全部取貨點都有填時，合計要等於送貨合計。
    也接受舊格式 {pickup, dropoff, scu}。"""
    if 'pickups' not in it and 'dropoffs' not in it:
        it = {'pickups': [{'place': it.get('pickup'), 'scu': it.get('scu')}],
              'dropoffs': [{'place': it.get('dropoff'), 'scu': it.get('scu')}]}
    supply = _points(it.get('pickups'), f'{label} 取貨', node)
    demand = _points(it.get('dropoffs'), f'{label} 送貨', node)
    if len(demand) == 1 and demand[0][1] is None and all(p[1] is not None for p in supply):
        demand[0][1] = sum(p[1] for p in supply)
    if any(p[1] is None for p in demand):
        raise RouteError(f'{label}：請填送貨的 SCU')
    total_out = sum(p[1] for p in demand)
    known = sum(p[1] for p in supply if p[1] is not None)
    if all(p[1] is not None for p in supply):
        if abs(known - total_out) > 1e-6:
            raise RouteError(f'{label}：取貨合計 {known:g} SCU、送貨合計 {total_out:g} SCU 不一樣')
    elif known >= total_out - 1e-6:
        raise RouteError(f'{label}：有填的取貨合計 {known:g} SCU 已經達到送貨合計 {total_out:g} SCU，'
                         '沒填 SCU 的取貨點沒有貨可拿')
    return supply, demand


def _pair(supply: list, demand: list, distance) -> tuple:
    """多個取貨點 → 多個送貨點：同一份合約的同一種貨物可以互相送 → (flows, collect)。

    flows：[(取貨點, 送貨點, SCU)]，有填 SCU 的取貨點，每次挑剩下最近的一組，送 min(剩餘取貨, 剩餘需求)。
    collect：沒填 SCU 的取貨點有兩個以上時 {pickups: [取貨點], drops: [(送貨點, 還缺的 SCU)], scu: 合計}，
    不猜各點有多少（見模組說明）；只有一個沒填的就是剩下的量，併進 flows。沒有沒填的回 None。"""
    left_out = [[n, scu] for n, scu in demand]
    flexible = [n for n, scu in supply if scu is None]
    left_in = [[n, scu] for n, scu in supply if scu is not None]
    rest = sum(scu for _, scu in left_out) - sum(scu for _, scu in left_in)
    if len(flexible) == 1:
        left_in.append([flexible[0], rest])
        flexible = []
    pairs = sorted((distance(a[0], b[0]), i, j) for i, a in enumerate(left_in) for j, b in enumerate(left_out))
    flows = []
    for _, i, j in pairs:
        amount = min(left_in[i][1], left_out[j][1])
        if amount <= 1e-9:
            continue
        flows.append((left_in[i][0], left_out[j][0], amount))
        left_in[i][1] -= amount
        left_out[j][1] -= amount
    if not flexible:
        return flows, None
    need = [(n, scu) for n, scu in left_out if scu > 1e-9]
    pickups = _chain(flexible, distance)
    # 方向：取貨串的最後一個點離送貨點近的那頭（另一頭就是出發時先去的）
    near = lambda n: min(distance(n, d) for d, _ in need)  # noqa: E731
    if near(pickups[0]) < near(pickups[-1]):
        pickups.reverse()
    drops = _chain(need, distance, node=lambda d: d[0], after=pickups[-1])
    return flows, {'pickups': pickups, 'drops': drops, 'scu': sum(a for _, a in drops)}


def plan_contracts(*, start_id: str, squads: list, contracts: list, end_mode: str = 'none',
                   visible_only: bool = False, start_fuel=None) -> dict:
    """squads：[{name, ship, quantum_drive, start}]；
    contracts：[{name, items: [{cargo, pickups: [{place, scu}], dropoffs: [{place, scu}]}]}]；
    end_mode：none（停在最後一站）／start（各隊回到自己的起點）；
    start_fuel：各隊的起始油量 {mode: pct／amount, value}（百分比照各自油箱算，油量超過油箱就是滿油），沒給＝滿油。"""
    w = nav.world(visible_only)

    def node(nid, label):
        n = w.nodes.get(nid) if isinstance(nid, str) and nid else None
        if not n or n.get('synthetic'):
            raise RouteError(f'{label}：找不到地點或沒有座標')
        return n

    if not isinstance(squads, list) or not squads:
        raise RouteError('請至少設定一個小隊')
    if len(squads) > MAX_SQUADS:
        raise RouteError(f'小隊最多 {MAX_SQUADS} 隊')
    if not isinstance(contracts, list) or not contracts:
        raise RouteError('請至少加一份合約')
    if len(contracts) > MAX_CONTRACTS:
        raise RouteError(f'合約最多 {MAX_CONTRACTS} 份')

    squad_infos = []
    for i, s in enumerate(squads, start=1):
        s = s if isinstance(s, dict) else {}
        name = str(s.get('name') or '').strip()[:30] or f'小隊 {i}'
        ship_id = str(s.get('ship') or '')
        if not ship_id:
            raise RouteError(f'{name}：請選船')
        info = nav.ship(ship_id, str(s.get('quantum_drive') or ''))
        start = node(str(s.get('start') or start_id or ''), f'{name} 起點')
        squad_infos.append({'index': i - 1, 'name': name, 'ship': info, 'cap': float(info.get('cargo_scu') or 0),
                            'external': bool(info.get('external_cargo')), 'start': start,
                            'end': start if end_mode == 'start' else None})
    max_cap = max(s['cap'] for s in squad_infos)
    if max_cap <= 0:
        raise RouteError('所有小隊的船都沒有貨艙')

    # 航段（OM 點繞行、跳躍點）跟船無關，各隊共用快取
    shared_paths, shared_routes = {}, {}
    planners = []
    for s in squad_infos:
        p = nav.Planner(w, s['ship'])
        p._paths, p._routes = shared_paths, shared_routes
        planners.append(p)

    def distance(a, b):
        return sum(st['distance'] for st in planners[0].route(a, b)) + (0.0 if a['system'] == b['system'] else 1e13)

    tasks = []
    for ci, c in enumerate(contracts, start=1):
        c = c if isinstance(c, dict) else {}
        cname = str(c.get('name') or '').strip()[:40] or f'合約 {ci}'
        items = c.get('items')
        if not isinstance(items, list) or not items:
            raise RouteError(f'{cname}：請至少加一項貨物')
        if len(items) > MAX_ITEMS:
            raise RouteError(f'{cname}：貨物最多 {MAX_ITEMS} 項')
        for ii, it in enumerate(items, start=1):
            it = it if isinstance(it, dict) else {}
            named = bool(str(it.get('cargo') or '').strip())
            iname = str(it.get('cargo') or '').strip()[:60] or f'貨物 {ii}'
            label = f'{cname} {iname}'
            supply, demand = _item_points(it, label, node)
            flows, collect = _pair(supply, demand, distance)
            common = {'contract': ci, 'contract_name': cname, 'item': ii, 'item_name': iname, 'item_named': named}
            for pickup, dropoff, scu in flows:
                parts = math.ceil(scu / max_cap - 1e-9)
                for k, part in enumerate(_split(scu, parts), start=1):
                    tasks.append({'id': len(tasks), **common, 'pickup': pickup, 'dropoff': dropoff,
                                  'pickups': [pickup], 'drops': [(dropoff, part)], 'unknown': False,
                                  'scu': part, 'part': k, 'parts': parts})
            if collect:
                if collect['scu'] > max_cap + 1e-9:
                    raise RouteError(f'{label}：{len(collect["pickups"])} 個取貨點沒填 SCU（不知道各點有多少，'
                                     f'要同一艘船一趟去完），剩下 {collect["scu"]:g} SCU 超過最大貨艙 {max_cap:g} SCU，'
                                     '請填各取貨點的 SCU 或換大一點的船')
                tasks.append({'id': len(tasks), **common, 'pickup': collect['pickups'][0],
                              'dropoff': collect['drops'][0][0], 'pickups': collect['pickups'],
                              'drops': collect['drops'], 'unknown': True, 'scu': collect['scu'],
                              'part': 1, 'parts': 1})
    if len(tasks) > MAX_TASKS:
        raise RouteError(f'拆成趟數後共 {len(tasks)} 趟，最多 {MAX_TASKS} 趟，請減少合約或換大一點的船')
    for task in tasks:
        # 外掛貨櫃（Hull 系列）只能在有外部貨運（裝卸碼頭）的站點裝卸（見 nav.World.external_ok）
        external_ok = all(w.external_ok(n) for n in [*task['pickups'], *(d for d, _ in task['drops'])])
        task['eligible'] = [s['index'] for s in squad_infos
                            if s['cap'] + 1e-9 >= task['scu'] and (external_ok or not s['external'])]
        if not task['eligible']:
            raise RouteError(f'{task["contract_name"]} {task["item_name"]}：沒有小隊載得了'
                             f'（貨艙不夠，或{w.external_rule}）')

    # 每個方案各自搜尋；最後每個方案再從所有方案找到的分配裡挑對它最好的（搜尋是啟發式，互相補位）
    evals = {key: [_Squad(s, planners[s['index']], _LEG_COST[key]) for s in squad_infos] for key, _ in OBJECTIVES}
    found = []
    for key, _ in OBJECTIVES:
        seqs = _assign(tasks, evals[key], key, time.monotonic() + SEARCH_SECONDS)
        found.append([_polish(evals[key][i], seq) for i, seq in enumerate(seqs)])
    # 站點平均：每個站點只給一隊，各隊航程（距離）平均（見模組說明 5）
    groups = _station_groups(tasks)
    station_eval = [_Squad(s, planners[s['index']], 'distance') for s in squad_infos]
    station_seqs = [_polish(station_eval[i], seq) for i, seq in enumerate(
        _assign_stations(groups, station_eval, time.monotonic() + SEARCH_SECONDS))]

    results, seen, systems = [], {}, set()
    for key, label in [*OBJECTIVES, (STATIONS_KEY, STATIONS_LABEL)]:
        if key == STATIONS_KEY:
            seqs = station_seqs
        else:
            seqs = min(found, key=lambda cand: _score(key, [evals[key][i].cost(seq) for i, seq in enumerate(cand)]))
        out_squads, allocation = [], []
        for s, seq in zip(squad_infos, seqs):
            plan = None
            if seq:
                events = _events_of(seq)
                plan = nav._build_plan(planners[s['index']], s['start'], events, list(range(len(events))),
                                       s['end'], key, s['name'], start_fuel)
                systems |= {s['start']['system']} | {st['to']['system_key'] for leg in plan['legs']
                                                      for st in leg['steps']}
                for task, sign in seq:
                    if sign > 0:
                        # 收集任務每個送貨點一列，取貨點列全部（pickups，各點量不知道）
                        for dropoff, amount in task['drops']:
                            allocation.append({k: task[k] for k in ('contract', 'contract_name', 'item', 'item_name',
                                                                   'part', 'parts', 'unknown')}
                                              | {'squad': s['index'], 'scu': amount,
                                                 'pickup': nav.node_brief(task['pickup']),
                                                 'pickups': [nav.node_brief(n) for n in task['pickups']],
                                                 'dropoff': nav.node_brief(dropoff)})
            out_squads.append({
                'index': s['index'], 'name': s['name'],
                'ship': {k: s['ship'].get(k) for k in SHIP_KEYS},
                'start': nav.node_brief(s['start'], True),
                'scu': sum(t['scu'] for t, sign in seq if sign > 0),
                'trips': sum(1 for _, sign in seq if sign > 0),
                # 這隊要去的站點數（不重複）
                'stations': len({sid for t, sign in seq if sign > 0 for sid in _station_ids(t)}),
                'plan': plan,
            })
        allocation.sort(key=lambda a: (a['contract'], a['item'], a['pickup']['name'], a['dropoff']['name'], a['part']))
        plans = [sq['plan'] for sq in out_squads if sq['plan']]
        times = [p['totals']['time'] for p in plans]
        fuels = [p['totals']['fuel'] for p in plans]
        sig = tuple(tuple((t['id'], sign) for t, sign in seq) for seq in seqs)
        results.append({
            'key': key, 'label': label, 'squads': out_squads, 'allocation': allocation,
            'totals': {
                'makespan': max(times) if times else 0.0,
                'time': sum(times),
                'fuel': None if any(f is None for f in fuels) else sum(fuels),
                'distance': sum(p['totals']['distance'] for p in plans),
                'refuels': sum(len(p['refuel_stops']) for p in plans),
            },
            'warnings': sorted({wn for p in plans for wn in p['warnings']}),
            'same_as': seen.get(sig),
            # 站點平均：有貨物相連而綁在一起的站點組數（比隊數少時有些隊分不到）
            **({'groups': len(groups)} if key == STATIONS_KEY else {}),
        })
        seen.setdefault(sig, key)
    return {
        'map': nav.star_map(w, systems or {s['start']['system'] for s in squad_infos}),
        'plans': results,
        'total_scu': sum(t['scu'] for t in tasks),
        'trips': len(tasks),
    }


MAX_SEQUENCE = 2 * MAX_TASKS


def evaluate_sequence(*, start_id: str, ship_id: str, qd_id: str = '', steps: list, end_mode: str = 'none',
                      name: str = '', visible_only: bool = False, start_fuel=None, end_id: str = '',
                      onboard=()) -> dict:
    """照給定的順序算一個小隊的航線（玩家在結果上拖拉調整順序後重算）。

    steps：[{place, kind: pickup／dropoff／stop（途經）, scu, cargo, contract, contract_name, item, item_name, item_named,
    scu_unknown}]。scu_unknown 的取貨（收集任務，各點量不知道）：同一趟（cargo）第一個取貨點預留這趟送貨的合計，
    其餘不加；這趟的取貨點都去過了才能送。
    檢查：同一份合約的同一種貨物要先取貨才能送、途中不超過貨艙、外掛貨櫃只停外部貨運站。
    end_id：最後要回去的地點（中途重新規劃過時是原起點），有給就不看 end_mode；
    onboard：出發時貨艙裡已經有的貨 [{contract, item, item_name, scu}]（中途重新規劃過）。"""
    w = nav.world(visible_only)
    if not isinstance(steps, list) or not steps:
        raise RouteError('沒有要跑的站點')
    if len(steps) > MAX_SEQUENCE:
        raise RouteError(f'站點最多 {MAX_SEQUENCE} 個')

    def node(nid, label):
        n = w.nodes.get(nid) if isinstance(nid, str) and nid else None
        if not n or n.get('synthetic'):
            raise RouteError(f'{label}：找不到地點或沒有座標')
        return n

    info = nav.ship(ship_id, qd_id)
    cap = float(info.get('cargo_scu') or 0)
    start = node(start_id, '起點')
    preload = onboard if isinstance(onboard, (list, tuple)) else []
    events, onboard, load = [], {}, 0.0
    for it in preload:
        it = it if isinstance(it, dict) else {}
        try:
            scu = float(it.get('scu') or 0)
        except (TypeError, ValueError):
            raise RouteError('貨艙裡的貨 SCU 格式錯誤')
        key = (it.get('contract'), str(it.get('item_name') or '').strip().lower(), it.get('item'))
        onboard[key] = onboard.get(key, 0.0) + scu
        load += scu
    initial_load = load
    preloaded = dict(onboard)
    # 收集任務（量不知道的取貨）：每一趟的送貨合計、還沒去的取貨點數
    unknown_total, unknown_left = {}, {}
    for st in steps:
        st = st if isinstance(st, dict) else {}
        c = str(st.get('cargo'))
        if st.get('kind') == 'pickup' and st.get('scu_unknown'):
            unknown_left[c] = unknown_left.get(c, 0) + 1
    for st in steps:
        st = st if isinstance(st, dict) else {}
        c = str(st.get('cargo'))
        if st.get('kind') == 'dropoff' and c in unknown_left:
            try:
                unknown_total[c] = unknown_total.get(c, 0.0) + float(st.get('scu') or 0)
            except (TypeError, ValueError):
                raise RouteError('SCU 格式錯誤')
    reserved = set()
    for i, st in enumerate(steps, start=1):
        st = st if isinstance(st, dict) else {}
        kind = st.get('kind')
        if kind == 'stop':     # 途經（中途插入的站點）
            events.append({'node': node(st.get('place'), f'第 {i} 站'), 'delta': 0.0, 'need': None, 'kind': 'stop'})
            continue
        if kind not in ('pickup', 'dropoff'):
            raise RouteError(f'第 {i} 站：動作不正確')
        n = node(st.get('place'), f'第 {i} 站')
        label = f'{st.get("contract_name") or ""} {st.get("item_name") or ""}'.strip()
        key = (st.get('contract'), str(st.get('item_name') or '').strip().lower(), st.get('item'))
        cargo = str(st.get('cargo'))
        if kind == 'pickup' and st.get('scu_unknown'):
            # 第一個取貨點預留整趟的量（扣掉出發前就在貨艙裡、已經預留過的）
            amount = 0.0
            if cargo not in reserved:
                reserved.add(cargo)
                amount = max(0.0, unknown_total.get(cargo, 0.0) - preloaded.get(key, 0.0))
            unknown_left[cargo] -= 1
            onboard[key] = onboard.get(key, 0.0) + amount
            load += amount
            if load > cap + 1e-9:
                raise RouteError(f'第 {i} 站 {n.get("name_zh") or n["name"]}：載貨 {load:g} SCU 超過貨艙 {cap:g} SCU')
            if info.get('external_cargo') and not w.external_ok(n):
                raise RouteError(f'{w.external_rule}：{n.get("name_zh") or n["name"]}')
            events.append({'node': n, 'delta': amount, 'need': None, 'kind': kind, 'cargo': st.get('cargo') or i,
                           'scu': None, **{k: st.get(k) for k in nav.LEG_EXTRA}, 'scu_unknown': True})
            continue
        try:
            scu = float(st.get('scu') or 0)
        except (TypeError, ValueError):
            raise RouteError(f'第 {i} 站：SCU 格式錯誤')
        if scu <= 0:
            raise RouteError(f'第 {i} 站：SCU 要大於 0')
        if kind == 'dropoff' and unknown_left.get(cargo, 0) > 0:
            raise RouteError(f'第 {i} 站 {n.get("name_zh") or n["name"]}：{label} 的取貨點還沒去完，'
                             '數量不知道，要全部取完才能送')
        if kind == 'pickup':
            onboard[key] = onboard.get(key, 0.0) + scu
            load += scu
            if load > cap + 1e-9:
                raise RouteError(f'第 {i} 站 {n.get("name_zh") or n["name"]}：載貨 {load:g} SCU 超過貨艙 {cap:g} SCU')
        else:
            if onboard.get(key, 0.0) + 1e-9 < scu:
                raise RouteError(f'第 {i} 站 {n.get("name_zh") or n["name"]}：{label} 要先取貨才能送')
            onboard[key] -= scu
            load -= scu
        if info.get('external_cargo') and not w.external_ok(n):
            raise RouteError(f'{w.external_rule}：{n.get("name_zh") or n["name"]}')
        events.append({'node': n, 'delta': scu if kind == 'pickup' else -scu, 'need': None, 'kind': kind,
                       # cargo：哪一趟（取貨、送貨同一個號碼；中途重新規劃靠它配對），沒給就用站序
                       'cargo': st.get('cargo') or i, 'scu': scu, **{k: st.get(k) for k in nav.LEG_EXTRA}})
    end = node(end_id, '終點') if end_id else (start if end_mode == 'start' else None)
    plan = nav._build_plan(nav.Planner(w, info), start, events, list(range(len(events))), end, 'custom',
                           name or '自訂順序', start_fuel, initial_load)
    return {'plan': plan, 'ship': {k: info.get(k) for k in SHIP_KEYS}}


def replan_squad(*, start_id: str, ship_id: str, qd_id: str = '', steps: list, onboard=(), stops=(),
                 end_id: str = '', name: str = '', visible_only: bool = False, start_fuel=None) -> dict:
    """中途重新規劃一個小隊還沒跑完的行程（可以插入新的站點）。

    start_id：現在的位置（最後一個已去過的站）；steps：還沒做的取貨／送貨（同一趟的 cargo 號碼一樣）；
    onboard：已經取了、還沒送的趟（cargo 號碼），它們在 steps 裡只剩送貨；stops：要插入的途經站點；
    end_id：最後要回去的地點（原本「回到起點」時是原起點）。
    順序重新排（跟一般航線同一套：取貨在送貨前、不超過貨艙，事件少時是精確解），成本用時間。"""
    w = nav.world(visible_only)

    def node(nid, label):
        n = w.nodes.get(nid) if isinstance(nid, str) and nid else None
        if not n or n.get('synthetic'):
            raise RouteError(f'{label}：找不到地點或沒有座標')
        return n

    steps = steps if isinstance(steps, list) else []
    stops = [s for s in (stops or []) if s]
    if not steps and not stops and not end_id:
        raise RouteError('沒有還沒跑的站點')
    if len(steps) + len(stops) > MAX_SEQUENCE:
        raise RouteError(f'站點最多 {MAX_SEQUENCE} 個')
    info = nav.ship(ship_id, qd_id)
    cap = float(info.get('cargo_scu') or 0)
    start = node(start_id, '目前位置')
    onboard = {str(c) for c in (onboard or [])}
    events, picks, base_load = [], {}, 0.0
    by_cargo: dict = {}
    for i, st in enumerate(steps, start=1):
        st = st if isinstance(st, dict) else {}
        if st.get('kind') not in ('pickup', 'dropoff'):
            raise RouteError(f'第 {i} 站：動作不正確')
        by_cargo.setdefault(str(st.get('cargo')), {'pickup': [], 'dropoff': []})[st['kind']].append(st)
    # 同一趟（cargo）：取貨可以好幾個點（收集任務，量不知道）、送貨可以好幾個點；取貨照原本順序，全部取完才送
    for cargo, group in by_cargo.items():
        drops, picks = group['dropoff'], group['pickup']
        if not drops:
            raise RouteError(f'{picks[0].get("contract_name") or ""} {picks[0].get("item_name") or ""}：缺少送貨站')
        try:
            amounts = [float(d.get('scu') or 0) for d in drops]
        except (TypeError, ValueError):
            raise RouteError('SCU 格式錯誤')
        total = sum(amounts)
        extra = {k: drops[0].get(k) for k in nav.LEG_EXTRA if k != 'scu_unknown'}
        unknown = any(p.get('scu_unknown') for p in picks)
        need = None
        if cargo in onboard:       # 已經取過（收集任務可能還有沒去的取貨點）：整趟的量已經在貨艙
            base_load += total
        elif not picks:
            raise RouteError(f'{drops[0].get("contract_name") or ""} {drops[0].get("item_name") or ""}：'
                             '還沒取貨，缺少取貨站')
        for k, p in enumerate(picks):
            delta = total if k == 0 and cargo not in onboard else 0.0
            events.append({'node': node(p.get('place'), '取貨站'), 'delta': delta, 'need': need, 'kind': 'pickup',
                           'cargo': drops[0].get('cargo'), 'scu': None if unknown else total, **extra,
                           **({'scu_unknown': True} if unknown else {})})
            need = len(events) - 1
        for d, amount in zip(drops, amounts):
            events.append({'node': node(d.get('place'), '送貨站'), 'delta': -amount, 'need': need, 'kind': 'dropoff',
                           'cargo': d.get('cargo'), 'scu': amount, **extra})
    for sid in stops:
        events.append({'node': node(sid, '插入的站點'), 'delta': 0.0, 'need': None, 'kind': 'stop'})
    if base_load > cap + 1e-9:
        raise RouteError(f'貨艙裡的貨 {base_load:g} SCU 超過貨艙 {cap:g} SCU')
    for e in events:
        if e['kind'] in ('pickup', 'dropoff') and info.get('external_cargo') and not w.external_ok(e['node']):
            raise RouteError(f'{w.external_rule}：{e["node"].get("name_zh") or e["node"]["name"]}')
    end = node(end_id, '終點') if end_id else None
    planner = nav.Planner(w, info)
    order = nav._order(planner, start, events, end, 'fastest', True, cap, base_load) if events else []
    plan = nav._build_plan(planner, start, events, order, end, 'custom', name or '重新規劃', start_fuel, base_load)
    return {'plan': plan, 'ship': {k: info.get(k) for k in SHIP_KEYS}}
