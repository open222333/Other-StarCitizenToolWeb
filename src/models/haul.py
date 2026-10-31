"""合約分配（玩家頁「航線 › 合約分配」）：多份運貨合約 × 多個小隊，算出每隊載哪些貨、照什麼順序跑。

輸入：
  - 合約（最多 MAX_CONTRACTS 份），每份有幾項貨物：{貨物名稱, 取貨點 [{地點, SCU}], 送貨點 [{地點, SCU}]}。
    貨物只能送到「同一份合約」的送貨點（同名貨物、不同合約也不能互相繳交）；
    同一項貨物有好幾個取貨點、送貨點時，先依距離把取貨點配給送貨點（_pair，近的先配；
    每個取貨點都一定會去，沒填 SCU 的平均分），變成幾組綁定的取貨→送貨。
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
"""

import math
import random
import time

from src.models import nav
from src.models.nav import RouteError

MAX_CONTRACTS = 10
MAX_ITEMS = 10
#: 每項貨物的取貨點／送貨點各最多幾個
MAX_POINTS = 10
MAX_SQUADS = 6
MAX_TASKS = 40
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
        """seq：[(任務, +1 取貨／-1 送貨)]；超過貨艙回 inf。"""
        if not seq:
            return 0.0
        cur, load, total = self.start, 0.0, 0.0
        for task, sign in seq:
            node = task['pickup'] if sign > 0 else task['dropoff']
            total += self.leg(cur, node, load)
            load += sign * task['scu']
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
        pick, drop = task['pickup'], task['dropoff']
        nodes, loads, load = [], [], 0.0
        for t, sign in seq:
            nodes.append(t['pickup'] if sign > 0 else t['dropoff'])
            load += sign * t['scu']
            loads.append(load)

        def leg(a, b):
            return self.leg(a, b, 0.0) if a is not None and b is not None else 0.0

        def around(i):
            return (self.start if i == 0 else nodes[i - 1]), (nodes[i] if i < n else self.end)

        best = (math.inf, None, None)
        for i in range(n + 1):
            if (loads[i - 1] if i else 0.0) + scu > cap + 1e-9:
                continue
            prev, nxt = around(i)
            base = leg(prev, nxt)
            c = leg(prev, pick) + leg(pick, drop) + leg(drop, nxt) - base
            if c < best[0]:
                best = (c, i, i)
            add_pick = leg(prev, pick) + leg(pick, nxt) - base
            peak = -math.inf
            for j in range(i + 1, n + 1):
                peak = max(peak, loads[j - 1])
                if peak + scu > cap + 1e-9:
                    break
                pj, nj = around(j)
                c = add_pick + leg(pj, drop) + leg(drop, nj) - leg(pj, nj)
                if c < best[0]:
                    best = (c, i, j)
        if best[1] is None:
            return math.inf, None
        _, i, j = best
        new = seq[:i] + [(task, 1)] + seq[i:j] + [(task, -1)] + seq[j:]
        return self.cost(new), new


def _score(objective: str, costs: list) -> float:
    if objective == 'time':
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


def _events_of(seq: list) -> list:
    """seq → nav 的事件（取貨／送貨，送貨要先取貨）。"""
    events, pick_index = [], {}
    for task, sign in seq:
        common = {'cargo': task['id'] + 1, 'scu': task['scu'], 'contract': task['contract'],
                  'contract_name': task['contract_name'], 'item': task['item'], 'item_name': task['item_name'],
                  'item_named': task['item_named']}
        if sign > 0:
            pick_index[task['id']] = len(events)
            events.append({'node': task['pickup'], 'delta': task['scu'], 'need': None, 'kind': 'pickup', **common})
        else:
            events.append({'node': task['dropoff'], 'delta': -task['scu'], 'need': pick_index[task['id']],
                           'kind': 'dropoff', **common})
    return events


def _polish(squad: _Squad, seq: list) -> list:
    """用 nav._order 再排一次（事件少時是精確解），比較好就換。"""
    if len(seq) <= 2:
        return seq
    events = _events_of(seq)
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


def _pair(supply: list, demand: list, distance) -> list:
    """多個取貨點 → 多個送貨點：同一份合約的同一種貨物可以互相送 → [(取貨點, 送貨點, SCU)]。

    每個取貨點都一定要去：沒填 SCU 的取貨點平均分掉「送貨合計 − 有填的取貨合計」
    （整數 SCU 拆成整數），所以每個點都至少拿一點；接著每次挑剩下最近的一組，送 min(剩餘取貨, 剩餘需求)。"""
    left_out = [[n, scu] for n, scu in demand]
    flexible = [n for n, scu in supply if scu is None]
    left_in = [[n, scu] for n, scu in supply if scu is not None]
    if flexible:
        rest = sum(scu for _, scu in left_out) - sum(scu for _, scu in left_in)
        shares = _split(rest, len(flexible))
        if min(shares) <= 1e-9:
            raise RouteError(f'沒填 SCU 的取貨點有 {len(flexible)} 個，剩下要取的只有 {rest:g} SCU，每個點都去不完')
        left_in += [[n, share] for n, share in zip(flexible, shares)]
    pairs = sorted((distance(a[0], b[0]), i, j) for i, a in enumerate(left_in) for j, b in enumerate(left_out))
    flows = []
    for _, i, j in pairs:
        amount = min(left_in[i][1], left_out[j][1])
        if amount <= 1e-9:
            continue
        flows.append((left_in[i][0], left_out[j][0], amount))
        left_in[i][1] -= amount
        left_out[j][1] -= amount
    return flows


def plan_contracts(*, start_id: str, squads: list, contracts: list, end_mode: str = 'none',
                   visible_only: bool = False) -> dict:
    """squads：[{name, ship, quantum_drive, start}]；
    contracts：[{name, items: [{cargo, pickups: [{place, scu}], dropoffs: [{place, scu}]}]}]；
    end_mode：none（停在最後一站）／start（各隊回到自己的起點）。"""
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
            flows = _pair(supply, demand, distance)
            for pickup, dropoff, scu in flows:
                parts = math.ceil(scu / max_cap - 1e-9)
                for k, part in enumerate(_split(scu, parts), start=1):
                    tasks.append({'id': len(tasks), 'contract': ci, 'contract_name': cname, 'item': ii,
                                  'item_name': iname, 'item_named': named, 'pickup': pickup, 'dropoff': dropoff,
                                  'scu': part,
                                  'part': k, 'parts': parts})
    if len(tasks) > MAX_TASKS:
        raise RouteError(f'拆成趟數後共 {len(tasks)} 趟，最多 {MAX_TASKS} 趟，請減少合約或換大一點的船')
    for task in tasks:
        # 外掛貨櫃（Hull 系列）只能在有外部貨運（裝卸碼頭）的站點裝卸（見 nav.World.external_ok）
        external_ok = w.external_ok(task['pickup']) and w.external_ok(task['dropoff'])
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

    results, seen, systems = [], {}, set()
    for key, label in OBJECTIVES:
        seqs = min(found, key=lambda cand: _score(key, [evals[key][i].cost(seq) for i, seq in enumerate(cand)]))
        out_squads, allocation = [], []
        for s, seq in zip(squad_infos, seqs):
            plan = None
            if seq:
                events = _events_of(seq)
                plan = nav._build_plan(planners[s['index']], s['start'], events, list(range(len(events))),
                                       s['end'], key, s['name'])
                systems |= {s['start']['system']} | {st['to']['system_key'] for leg in plan['legs']
                                                      for st in leg['steps']}
                for task, sign in seq:
                    if sign > 0:
                        allocation.append({k: task[k] for k in ('contract', 'contract_name', 'item', 'item_name',
                                                               'scu', 'part', 'parts')}
                                          | {'squad': s['index'], 'pickup': nav.node_brief(task['pickup']),
                                             'dropoff': nav.node_brief(task['dropoff'])})
            out_squads.append({
                'index': s['index'], 'name': s['name'],
                'ship': {k: s['ship'].get(k) for k in SHIP_KEYS},
                'start': nav.node_brief(s['start'], True),
                'scu': sum(t['scu'] for t, sign in seq if sign > 0),
                'trips': sum(1 for _, sign in seq if sign > 0),
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
        })
        seen.setdefault(sig, key)
    return {
        'map': nav.star_map(w, systems or {s['start']['system'] for s in squad_infos}),
        'plans': results,
        'total_scu': sum(t['scu'] for t in tasks),
        'trips': len(tasks),
    }
