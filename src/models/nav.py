"""量子航行航線規劃（唯讀，玩家頁「航線」分頁）。

資料：
  - starmap_master：地點的絕對座標 pos（公尺，星系座標系，星體自轉角度 0）、
    星體半徑 size、量子阻擋半徑 obstruction_radius、跨星系跳躍點 jump_links
    （地點同步項目，見 src/models/starmap.py 的 apply_positions）
  - ship_nav_master：艦船預設量子引擎的速度、啟動時間、油箱、可達距離
    （同上，見 src/scdata.py 的 map_ship_nav）

演算法：
  1. 航段：兩點走直線；直線穿過某顆星體的阻擋球（obstruction_radius）就改經過那顆星體的
     OM 點（北極、南極、赤道四方向，離中心＝星體半徑 × OM_RADIUS_RATIO），遞迴最多
     MAX_DETOUR_DEPTH 層。端點在星體表面（或阻擋球內）時，自己那顆星體只有「直線穿過星體本身」才算擋住。
  2. 多站點順序：自動排序用 Held-Karp 動態規劃（取貨一定在送貨前、載貨量不超過貨艙），
     事件數超過 EXACT_LIMIT 改用貪婪＋相鄰交換改良。
  3. 方案：最快（距離 ÷ 量子速度＋每段啟動時間）、最省油（距離 × 每公尺耗油 × 載重係數）、
     最順路（量子跳躍次數最少，其次距離最短）。
  4. 載重：載重係數＝1 + 貨重 ÷ 船重（每 SCU 以 KG_PER_SCU 估算），乘在油耗上，啟動時間乘它的平方根。
  5. 外掛貨櫃（Hull 系列）載貨時不能停地表站點，只能停太空站。

座標是自轉角度 0 時的位置，地表站點在遊戲裡會跟著星體自轉，距離是估算值。
"""

import math
import threading
import time

from src.mongo import get_db

BODY_TYPES = ('Planet', 'Moon')
#: 不列入地點選單的類型（一般小行星群：數量多、不能量子定位）
PLACE_EXCLUDE_TYPES = ('Asteroid',)
#: 地表判定：離所屬星體中心 ≤ 半徑 × 這個倍數
SURFACE_RATIO = 1.06
#: 星體本身的實心半徑（判斷直線是否穿過星體）
SOLID_RATIO = 0.97
#: OM 點離星體中心的距離（星體半徑的倍數；Stanton 實測約 1.44–1.47）
OM_RADIUS_RATIO = 1.45
MAX_DETOUR_DEPTH = 3
EXACT_LIMIT = 11
#: 估算貨重：每 SCU 公斤數
KG_PER_SCU = 1000
#: 沒選船時用的預設量子引擎
DEFAULT_SHIP = {'id': None, 'name': '', 'name_zh': None, 'qt_speed': 2.0e8, 'qt_spool': 5.0,
                'qt_fuel_per_m': None, 'qt_fuel_capacity': None, 'qt_range': None, 'cargo_scu': None,
                'external_cargo': False, 'mass_total': None}
MAX_WAYPOINTS = 12
MAX_CARGO = 8
CACHE_TTL = 300

PLANS = (
    ('fastest', '最快'),
    ('fuel', '最省油'),
    ('simple', '最順路'),
)


class RouteError(ValueError):
    pass


def _dist(a, b) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _seg_point_distance(a, b, c):
    """點 c 到線段 ab 的最短距離與投影參數 t（0..1）。"""
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    ab2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
    if ab2 == 0:
        return _dist(a, c), 0.0
    t = max(0.0, min(1.0, (ac[0] * ab[0] + ac[1] * ab[1] + ac[2] * ab[2]) / ab2))
    p = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return _dist(p, c), t


# ── 地圖（快取） ─────────────────────────────────────────────

class World:
    """一次載入的地點、星體、OM 點、跳躍點。"""

    def __init__(self, rows: list):
        self.nodes: dict = {}
        by_id = {r['_id']: r for r in rows}
        for r in rows:
            pos = r.get('pos') or {}
            if not all(isinstance(pos.get(k), (int, float)) for k in ('x', 'y', 'z')):
                continue
            qt = r.get('qt_valid')
            self.nodes[r['_id']] = {
                'id': r['_id'],
                'name': r.get('name') or '',
                'name_zh': r.get('name_zh'),
                'type': r.get('type') or '',
                'type_zh': r.get('type_zh'),
                'system': (r.get('pos_system') or r.get('system_name') or '').lower(),
                'system_name': r.get('system_name'),
                'system_name_zh': r.get('system_name_zh'),
                'path_zh': r.get('path_zh') or [],
                'p': (float(pos['x']), float(pos['y']), float(pos['z'])),
                'qt_valid': bool(r.get('quantum_travel') if qt is None else qt),
                'radius': float(r.get('size') or 0),
                'obstruction': float(r.get('obstruction_radius') or 0),
                'jump_links': r.get('jump_links') or [],
                'parent_uuid': r.get('parent_uuid'),
                'named': bool(r.get('is_named', bool(r.get('name')))),
            }
        # 星體（會擋航線）：有半徑的行星、衛星
        self.bodies = [n for n in self.nodes.values() if n['type'] in BODY_TYPES and n['radius'] > 0]
        for b in self.bodies:
            b['obstruction'] = max(b['obstruction'], b['radius'])
        bodies_by_id = {b['id']: b for b in self.bodies}
        # 每個地點所屬星體（上層鏈最近的行星／衛星）、是否在地表
        for n in self.nodes.values():
            body, cur, seen = None, n['parent_uuid'], set()
            while cur and cur not in seen:
                seen.add(cur)
                if cur in bodies_by_id:
                    body = bodies_by_id[cur]
                    break
                cur = (by_id.get(cur) or {}).get('parent_uuid')
            n['body'] = body['id'] if body else None
            # 選地點用的分組：星體本身算自己那一組，其他地點歸所屬星體，都不是的歸「太空」
            group = n if n['type'] in BODY_TYPES and n['radius'] > 0 else body
            n['group'] = group['id'] if group else None
            n['group_name'] = group['name'] if group else None
            n['group_name_zh'] = group.get('name_zh') if group else None
            n['group_type'] = group['type'] if group else None
            n['surface'] = bool(body and n['type'] not in BODY_TYPES
                                and _dist(n['p'], body['p']) <= body['radius'] * SURFACE_RATIO)
        # OM 點（每顆星體 6 個）
        self.oms: dict = {}
        for b in self.bodies:
            r = max(b['radius'] * OM_RADIUS_RATIO, b['obstruction'] * 1.1)
            x, y, z = b['p']
            offsets = ((0, 0, r), (0, 0, -r), (0, r, 0), (0, -r, 0), (r, 0, 0), (-r, 0, 0))
            items = []
            for i, (dx, dy, dz) in enumerate(offsets, start=1):
                om = {'id': f'om:{b["id"]}:{i}', 'name': f'{b["name"]} OM-{i}',
                      'name_zh': f'{b.get("name_zh") or b["name"]} OM-{i}',
                      'type': 'OrbitalMarker', 'type_zh': None, 'system': b['system'],
                      'system_name': b['system_name'], 'system_name_zh': b['system_name_zh'],
                      'path_zh': [*b['path_zh'], b.get('name_zh') or b['name']],
                      'p': (x + dx, y + dy, z + dz), 'qt_valid': True, 'radius': 0.0, 'obstruction': 0.0,
                      'jump_links': [], 'parent_uuid': b['id'], 'body': b['id'], 'surface': False,
                      'group': b['id'], 'group_name': b['name'], 'group_name_zh': b.get('name_zh'),
                      'group_type': b['type'],
                      'named': True, 'synthetic': True}
                self.nodes[om['id']] = om
                items.append(om)
            self.oms[b['id']] = items
        self.bodies_by_system: dict = {}
        for b in self.bodies:
            self.bodies_by_system.setdefault(b['system'], []).append(b)
        # 跳躍點：星系 → [(入口, 出口)]
        self.jump_points: dict = {}
        for n in list(self.nodes.values()):
            for link in n['jump_links']:
                exit_ = self.nodes.get(link.get('to'))
                if exit_ and exit_['system'] != n['system']:
                    self.jump_points.setdefault(n['system'], []).append((n, exit_))

    def blocker(self, a: dict, b: dict):
        """直線 a→b 第一個擋住的星體（離 a 最近的），沒有回 None。"""
        if a['system'] != b['system']:
            return None
        hit, best_t = None, 2.0
        for body in self.bodies_by_system.get(a['system'], []):
            if body['id'] in (a['id'], b['id']):
                continue
            radius = body['obstruction']
            # 端點就在這顆星體上或阻擋球內：只在穿過星體本身時算擋住
            for end in (a, b):
                if end.get('body') == body['id'] or _dist(end['p'], body['p']) < radius:
                    radius = body['radius'] * SOLID_RATIO
                    break
            d, t = _seg_point_distance(a['p'], b['p'], body['p'])
            if d < radius and 0.0 < t < 1.0 and t < best_t:
                hit, best_t = body, t
        return hit


_cache: dict = {}
_lock = threading.Lock()


def world(visible_only: bool = False) -> World:
    key = bool(visible_only)
    with _lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1]
    filt = {'is_current': True, 'pos': {'$ne': None}}
    if visible_only:
        filt['player_visible'] = {'$ne': False}
    fields = {'name': 1, 'name_zh': 1, 'type': 1, 'type_zh': 1, 'pos_system': 1, 'system_name': 1,
              'system_name_zh': 1, 'path_zh': 1, 'pos': 1, 'qt_valid': 1, 'quantum_travel': 1,
              'size': 1, 'obstruction_radius': 1, 'jump_links': 1, 'parent_uuid': 1, 'is_named': 1}
    w = World(list(get_db()['starmap_master'].find(filt, fields)))
    with _lock:
        _cache[key] = (time.time(), w)
    return w


def clear_cache():
    with _lock:
        _cache.clear()


def node_brief(n: dict) -> dict:
    return {'id': n['id'], 'name': n['name'], 'name_zh': n.get('name_zh'), 'type': n['type'],
            'type_zh': n.get('type_zh'), 'system': n.get('system_name'),
            'system_zh': n.get('system_name_zh'), 'path_zh': n.get('path_zh') or [],
            'surface': bool(n.get('surface')), 'synthetic': bool(n.get('synthetic')),
            'group': n.get('group'), 'group_name': n.get('group_name'), 'group_name_zh': n.get('group_name_zh'),
            'group_type': n.get('group_type')}


def places(visible_only: bool = False) -> list:
    """可以當起點／站點的地點（有座標、有名稱）。"""
    w = world(visible_only)
    rows = [node_brief(n) for n in w.nodes.values()
            if not n.get('synthetic') and n['named'] and n['name'] and n['type'] not in PLACE_EXCLUDE_TYPES]
    rows.sort(key=lambda r: (r['system'] or '', '/'.join(r['path_zh']), r['name']))
    return rows


# ── 艦船 ─────────────────────────────────────────────────────

SHIP_FIELDS = {'name': 1, 'class_name': 1, 'size': 1, 'qt_speed': 1, 'qt_spool': 1, 'qt_fuel_capacity': 1,
               'qt_range': 1, 'qt_fuel_per_m': 1, 'cargo_scu': 1, 'external_cargo': 1, 'mass_total': 1}


def _ship_row(r: dict, name_zh) -> dict:
    out = {'id': r['_id'], 'name': r.get('name') or r.get('class_name') or '', 'name_zh': name_zh}
    for k in SHIP_FIELDS:
        if k != 'name':
            out[k] = r.get(k)
    return out


def ships() -> list:
    """有量子引擎的太空船（中文名稱取 vehicle_master 的 name_zh）。"""
    db = get_db()
    rows = list(db['ship_nav_master'].find({'is_current': {'$ne': False}}, SHIP_FIELDS))
    names_zh = {r['_id']: r.get('name_zh') for r in db['vehicle_master'].find(
        {'_id': {'$in': [r['_id'] for r in rows]}}, {'name_zh': 1})}
    out = [_ship_row(r, names_zh.get(r['_id'])) for r in rows]
    out.sort(key=lambda r: r['name'].lower())
    return out


def ship(ship_id) -> dict:
    if not ship_id:
        return dict(DEFAULT_SHIP)
    db = get_db()
    r = db['ship_nav_master'].find_one({'_id': ship_id}, SHIP_FIELDS)
    if not r:
        raise RouteError('找不到這艘船的量子航行資料')
    zh = (db['vehicle_master'].find_one({'_id': ship_id}, {'name_zh': 1}) or {}).get('name_zh')
    row = _ship_row(r, zh)
    return {**DEFAULT_SHIP, **{k: v for k, v in row.items() if v is not None}}


# ── 規劃 ─────────────────────────────────────────────────────

class Planner:
    def __init__(self, w: World, ship_info: dict):
        self.w = w
        self.ship = ship_info
        self._paths: dict = {}
        self._routes: dict = {}

    def load_factor(self, load_scu: float) -> float:
        mass = self.ship.get('mass_total')
        if not load_scu or not mass:
            return 1.0
        return 1.0 + (load_scu * KG_PER_SCU) / mass

    def path(self, a: dict, b: dict, depth: int = 0) -> list:
        """a→b 的中繼點清單（含頭尾，同星系）。被擋住就經過擋住那顆星體的 OM 點。"""
        key = (a['id'], b['id'], depth)
        if key in self._paths:
            return self._paths[key]
        body = self.w.blocker(a, b)
        if body is None or depth >= MAX_DETOUR_DEPTH:
            result = [a, b]
        else:
            best, best_len = None, math.inf
            for om in self.w.oms.get(body['id'], []):
                if om['id'] in (a['id'], b['id']):
                    continue
                cand = self.path(a, om, depth + 1) + self.path(om, b, depth + 1)[1:]
                length = sum(_dist(cand[i]['p'], cand[i + 1]['p']) for i in range(len(cand) - 1)) \
                    + len(cand) * 1e6   # 距離差不多時少跳一次比較好
                if length < best_len:
                    best, best_len = cand, length
            result = best or [a, b]
        self._paths[key] = result
        return result

    def route(self, a: dict, b: dict) -> list:
        """a→b 的步驟 [{from, to, kind: qt|jump, distance}]，跨星系經過跳躍點。"""
        key = (a['id'], b['id'])
        if key in self._routes:
            return self._routes[key]
        if a['id'] == b['id']:
            steps = []
        elif a['system'] == b['system']:
            pts = self.path(a, b)
            steps = [{'from': pts[i], 'to': pts[i + 1], 'kind': 'qt',
                      'distance': _dist(pts[i]['p'], pts[i + 1]['p'])} for i in range(len(pts) - 1)]
        else:
            chain = self._system_chain(a['system'], b['system'])
            if not chain:
                raise RouteError(f'找不到從 {a.get("system_name_zh") or a.get("system_name") or a["system"]} 到 '
                                 f'{b.get("system_name_zh") or b.get("system_name") or b["system"]} 的跳躍點')
            steps, cur = [], a
            for entry, exit_ in chain:
                steps += self.route(cur, entry)
                steps.append({'from': entry, 'to': exit_, 'kind': 'jump', 'distance': 0.0})
                cur = exit_
            steps += self.route(cur, b)
        self._routes[key] = steps
        return steps

    def _system_chain(self, src: str, dst: str) -> list:
        """星系之間經過的跳躍點 [(入口, 出口)]（BFS，跳躍次數最少）。"""
        prev = {src: None}
        queue = [src]
        while queue:
            sys_ = queue.pop(0)
            if sys_ == dst:
                break
            for entry, exit_ in self.w.jump_points.get(sys_, []):
                if exit_['system'] not in prev:
                    prev[exit_['system']] = (sys_, entry, exit_)
                    queue.append(exit_['system'])
        if dst not in prev:
            return []
        chain, cur = [], dst
        while prev[cur]:
            sys_, entry, exit_ = prev[cur]
            chain.append((entry, exit_))
            cur = sys_
        return list(reversed(chain))

    def step_metrics(self, step: dict, load: float) -> dict:
        if step['kind'] == 'jump':
            return {'time': 0.0, 'fuel': 0.0, 'jumps': 0}
        lf = self.load_factor(load)
        d = step['distance']
        speed = self.ship.get('qt_speed') or DEFAULT_SHIP['qt_speed']
        spool = (self.ship.get('qt_spool') or 0) * math.sqrt(lf)
        per_m = self.ship.get('qt_fuel_per_m')
        return {'time': d / speed + spool, 'fuel': d * per_m * lf if per_m else None, 'jumps': 1}

    def leg_cost(self, a: dict, b: dict, load: float, plan: str) -> float:
        steps = self.route(a, b)
        if not steps:
            return 0.0
        total_d = sum(s['distance'] for s in steps)
        if plan == 'simple':
            jumps = sum(1 for s in steps if s['kind'] == 'qt')
            return jumps * 1e15 + total_d
        ms = [self.step_metrics(s, load) for s in steps]
        if plan == 'fuel':
            if self.ship.get('qt_fuel_per_m'):
                return sum(m['fuel'] or 0 for m in ms) + len(steps) * 1e-6
            return total_d
        return sum(m['time'] for m in ms)


def _order(planner: Planner, start: dict, events: list, end, plan: str, auto: bool, capacity) -> list:
    """事件順序（events 的 index）。事件：{node, delta（+取貨／−送貨／0 途經）, need（要先完成的事件 index）}"""
    n = len(events)
    if not auto or n <= 1:
        return list(range(n))

    def cost(a, b, load):
        return planner.leg_cost(a, b, load, plan)

    def feasible(i, mask, load):
        e = events[i]
        if e['need'] is not None and not (mask >> e['need']) & 1:
            return False
        return capacity is None or load + e['delta'] <= capacity + 1e-9

    def load_of(mask):
        return sum(events[i]['delta'] for i in range(n) if (mask >> i) & 1)

    def tail(k, load):
        return cost(events[k]['node'], end, load) if end else 0.0

    if n <= EXACT_LIMIT:
        full = (1 << n) - 1
        dp = [dict() for _ in range(1 << n)]          # dp[mask][last] = (成本, 上一個)
        for i in range(n):
            if feasible(i, 0, 0.0):
                dp[1 << i][i] = (cost(start, events[i]['node'], 0.0), None)
        for mask in range(1, full + 1):
            if not dp[mask]:
                continue
            load = load_of(mask)
            for last, (c, _) in dp[mask].items():
                for j in range(n):
                    if (mask >> j) & 1 or not feasible(j, mask, load):
                        continue
                    nc = c + cost(events[last]['node'], events[j]['node'], load)
                    nm = mask | (1 << j)
                    if j not in dp[nm] or nc < dp[nm][j][0]:
                        dp[nm][j] = (nc, last)
        if not dp[full]:
            raise RouteError('貨艙容量不足，排不出可行的取送順序')
        final_load = load_of(full)
        best_last = min(dp[full], key=lambda k: dp[full][k][0] + tail(k, final_load))
        order, mask, last = [], full, best_last
        while last is not None:
            order.append(last)
            prev = dp[mask][last][1]
            mask &= ~(1 << last)
            last = prev
        return list(reversed(order))

    # 事件太多：貪婪（每次挑成本最低的可行事件）＋相鄰交換改良
    order, mask, cur, load = [], 0, start, 0.0
    while len(order) < n:
        cands = [i for i in range(n) if not (mask >> i) & 1 and feasible(i, mask, load)]
        if not cands:
            raise RouteError('貨艙容量不足，排不出可行的取送順序')
        i = min(cands, key=lambda k: cost(cur, events[k]['node'], load))
        order.append(i)
        mask |= 1 << i
        load += events[i]['delta']
        cur = events[i]['node']

    def total(seq):
        c, cur_, ld, done = 0.0, start, 0.0, 0
        for i in seq:
            if not feasible(i, done, ld):
                return math.inf
            c += cost(cur_, events[i]['node'], ld)
            ld += events[i]['delta']
            done |= 1 << i
            cur_ = events[i]['node']
        return c + (cost(cur_, end, ld) if end else 0.0)

    best = total(order)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            cand = order[:i] + [order[i + 1], order[i]] + order[i + 2:]
            c = total(cand)
            if c < best - 1e-9:
                order, best, improved = cand, c, True
    return order


def _build_plan(planner: Planner, start, events, order, end, key, label) -> dict:
    legs = []
    cur, load = start, 0.0
    targets = [(events[i]['node'], events[i]) for i in order] + ([(end, None)] if end else [])
    totals = {'distance': 0.0, 'time': 0.0, 'fuel': 0.0, 'jumps': 0}
    has_fuel = True
    for target, event in targets:
        leg = {'distance': 0.0, 'time': 0.0, 'fuel': 0.0, 'jumps': 0}
        out_steps = []
        for s in planner.route(cur, target):
            m = planner.step_metrics(s, load)
            out_steps.append({'from': node_brief(s['from']), 'to': node_brief(s['to']), 'kind': s['kind'],
                              'distance': s['distance'], 'time': m['time'], 'fuel': m['fuel']})
            leg['distance'] += s['distance']
            leg['time'] += m['time']
            leg['jumps'] += m['jumps']
            if m['fuel'] is None:
                has_fuel = False
            else:
                leg['fuel'] += m['fuel']
        load_before = load
        if event:
            load += event['delta']
        legs.append({
            'to': node_brief(target),
            'action': event['kind'] if event else 'end',
            'cargo': event.get('cargo') if event else None,
            'scu': event.get('scu') if event else None,
            'load_before': load_before,
            'load_after': load,
            'steps': out_steps,
            **leg,
        })
        for k in totals:
            totals[k] += leg[k]
        cur = target
    if not has_fuel:
        totals['fuel'] = None
        for leg in legs:
            leg['fuel'] = None
    return {'key': key, 'label': label, 'start': node_brief(start), 'legs': legs, 'totals': totals,
            'warnings': []}


def plan_route(*, start_id: str, waypoints: list, cargo: list, end_mode: str = 'none', end_id: str = '',
               auto_order: bool = True, ship_id: str = '', external_cargo=None,
               visible_only: bool = False) -> dict:
    """規劃航線，回傳三種方案。

    waypoints：[地點 id]；cargo：[{pickup, dropoff, scu}]；end_mode：none／start（回到起點）／fixed（end_id）。
    external_cargo：None = 依船自動判斷（Hull 系列）。
    """
    w = world(visible_only)
    ship_info = ship(ship_id)
    if external_cargo is None:
        external_cargo = bool(ship_info.get('external_cargo'))

    def node(nid, label):
        n = w.nodes.get(nid) if isinstance(nid, str) and nid else None
        if not n or n.get('synthetic'):
            raise RouteError(f'{label}：找不到地點或沒有座標')
        return n

    if len(waypoints) > MAX_WAYPOINTS:
        raise RouteError(f'途經站點最多 {MAX_WAYPOINTS} 個')
    if len(cargo) > MAX_CARGO:
        raise RouteError(f'貨運最多 {MAX_CARGO} 筆')
    start = node(start_id, '起點')
    events = []
    for i, wid in enumerate(waypoints, start=1):
        events.append({'node': node(wid, f'站點 {i}'), 'delta': 0.0, 'need': None, 'kind': 'stop'})
    total_cargo = 0.0
    for i, c in enumerate(cargo, start=1):
        c = c if isinstance(c, dict) else {}
        try:
            scu = float(c.get('scu') or 0)
        except (TypeError, ValueError):
            raise RouteError(f'貨運 {i}：SCU 格式錯誤')
        if scu <= 0:
            raise RouteError(f'貨運 {i}：SCU 要大於 0')
        total_cargo += scu
        pick = len(events)
        events.append({'node': node(c.get('pickup'), f'貨運 {i} 取貨'), 'delta': scu, 'need': None,
                       'kind': 'pickup', 'cargo': i, 'scu': scu})
        events.append({'node': node(c.get('dropoff'), f'貨運 {i} 送貨'), 'delta': -scu, 'need': pick,
                       'kind': 'dropoff', 'cargo': i, 'scu': scu})
    end = None
    if end_mode == 'start':
        end = start
    elif end_mode == 'fixed':
        end = node(end_id, '終點')
    if not events and end is None:
        raise RouteError('請至少加一個站點、貨運或終點')

    capacity = ship_info.get('cargo_scu') if ship_info.get('id') else None
    if capacity is not None and cargo:
        biggest = max(e['scu'] for e in events if e['kind'] == 'pickup')
        if biggest > capacity:
            raise RouteError(f'單筆貨運 {biggest:g} SCU 超過貨艙容量 {capacity:g} SCU')
    if external_cargo and cargo:
        bad = [e['node'] for e in events if e['kind'] in ('pickup', 'dropoff') and e['node']['surface']]
        if bad:
            names = '、'.join(dict.fromkeys(n.get('name_zh') or n['name'] for n in bad))
            raise RouteError(f'外掛貨櫃只能停太空站：{names}')

    planner = Planner(w, ship_info)
    plans, seen = [], {}
    for key, label in PLANS:
        order = _order(planner, start, events, end, key, auto_order, capacity)
        plan = _build_plan(planner, start, events, order, end, key, label)
        sig = tuple((leg['to']['id'], leg['action'], leg['cargo']) for leg in plan['legs']) + \
            tuple(s['to']['id'] for leg in plan['legs'] for s in leg['steps'])
        plan['same_as'] = seen.get(sig)
        seen.setdefault(sig, key)
        fuel_cap, rng = ship_info.get('qt_fuel_capacity'), ship_info.get('qt_range')
        if fuel_cap and plan['totals']['fuel'] and plan['totals']['fuel'] > fuel_cap:
            plan['warnings'].append('fuel_over_capacity')
        if rng and any(s['distance'] > rng for leg in plan['legs'] for s in leg['steps']):
            plan['warnings'].append('step_over_range')
        plans.append(plan)
    return {
        'ship': {k: ship_info.get(k) for k in ('id', 'name', 'name_zh', 'qt_speed', 'qt_spool',
                                               'qt_fuel_capacity', 'qt_range', 'cargo_scu', 'mass_total')},
        'external_cargo': bool(external_cargo),
        'total_cargo_scu': total_cargo,
        'plans': plans,
    }
