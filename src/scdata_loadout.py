"""配裝模擬用的兩個主檔 mapper（scunpacked-data，見 src/models/loadout.py）。

  - ship-items.json → ship_item_master：艦船配件（武器、飛彈、護盾、電源、冷卻、量子、雷達…）的
    精簡數值（stats）、可裝的子槽（ports，例如砲塔上的武器槽、飛彈架上的飛彈槽）、標籤
  - ships.json      → ship_loadout_master：每艘船的掛點樹（只留配裝相關的槽）、船體／裝甲／
    穿透倍率／飛行等不隨配件變動的數值

不存 raw（兩個檔案加起來快 60 MB），要新增欄位就改這裡再重跑「配裝」同步。
"""

from typing import Optional

from src.sc_zh import item_name_zh, vehicle_name_zh, vehicle_role_zh

#: 配裝模擬看得到的配件種類（其餘像門、螢幕、座位、燃料箱、推進器都不列）
LOADOUT_TYPES = {
    'WeaponGun', 'Turret', 'TurretBase', 'MissileLauncher', 'Missile', 'BombLauncher', 'Bomb',
    'Shield', 'PowerPlant', 'Cooler', 'QuantumDrive', 'JumpDrive', 'Radar',
    'WeaponDefensive', 'WeaponMining', 'MiningModifier', 'SalvageHead', 'TractorBeam',
}

DAMAGE_KEYS = ('Physical', 'Energy', 'Distortion', 'Thermal', 'Biochemical', 'Stun')


def _num(value, default=None):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _real_name(value) -> str:
    text = (value or '').strip() if isinstance(value, str) else ''
    return '' if (not text or '<=' in text or text.startswith('@')) else text


def _dmg(d) -> dict:
    """傷害表 → 只留非零的種類，小寫 key（physical／energy／distortion…）。"""
    if not isinstance(d, dict):
        return {}
    return {k.lower(): d[k] for k in DAMAGE_KEYS if _num(d.get(k))}


def _range_map(d) -> dict:
    """{Physical: {Minimum, Maximum}} → {physical: [min, max]}。"""
    if not isinstance(d, dict):
        return {}
    out = {}
    for k in DAMAGE_KEYS:
        v = d.get(k)
        if isinstance(v, dict):
            out[k.lower()] = [_num(v.get('Minimum'), 0), _num(v.get('Maximum'), 0)]
    return out


def compat_types(port: dict) -> list:
    """槽位可裝的種類 → ['WeaponGun.Gun', 'Turret', 'Radar.MidRangeRadar', …]（沒有子類就只有主類）。"""
    out = []
    for c in port.get('CompatibleTypes') or []:
        if not isinstance(c, dict) or not c.get('Type'):
            continue
        subs = [s for s in c.get('SubTypes') or [] if s]
        out += [f"{c['Type']}.{s}" for s in subs] if subs else [c['Type']]
    if not out:
        out = [t for t in port.get('Types') or [] if isinstance(t, str)]
    return out


def _base(t: str) -> str:
    return (t or '').split('.')[0]


# ─────────────────────────────────────────── ship-items.json

def _weapon_stats(std: dict) -> dict:
    w = std.get('Weapon') if isinstance(std.get('Weapon'), dict) else {}
    ammo = std.get('Ammunition') if isinstance(std.get('Ammunition'), dict) else {}
    dmg = w.get('Damage') if isinstance(w.get('Damage'), dict) else {}
    pen = ammo.get('Penetration') if isinstance(ammo.get('Penetration'), dict) else {}
    modes = [m for m in w.get('Modes') or [] if isinstance(m, dict)]
    mode = modes[0] if modes else {}
    out = {
        'alpha': _num(dmg.get('AlphaTotal'), 0),
        'dps': _num(dmg.get('DpsTotal'), _num(dmg.get('Burst'), 0)),
        'sustained': _num(dmg.get('Sustained'), _num(dmg.get('DpsTotal'), 0)),
        'damage': _dmg(dmg.get('Alpha')),
        'rpm': _num(w.get('RateOfFire'), _num(mode.get('RoundsPerMinute'))),
        'fire_mode': mode.get('LocalisedName') or mode.get('Name'),
        'speed': _num(ammo.get('Speed')),
        'range': _num(w.get('EffectiveRange'), _num(ammo.get('Range'))),
        'ammo': _num(w.get('Capacity'), _num(ammo.get('Capacity'))),
        # 穿透：基礎穿透距離（公尺）與近／遠端半徑
        'pen_distance': _num(pen.get('BasePenetrationDistance')),
        'pen_near': _num(pen.get('NearRadius')),
        'pen_far': _num(pen.get('FarRadius')),
    }
    if isinstance(w.get('Consumption'), dict):       # 能量武器：用電容，不用彈藥
        out['ammo'] = None
        out['energy'] = True
    return out


def _turret_stats(std: dict) -> dict:
    t = std.get('Turret') if isinstance(std.get('Turret'), dict) else {}
    out = {}
    for m in t.get('MovementList') or []:
        if not isinstance(m, dict):
            continue
        for key, axis in (('yaw', 'YawAxis'), ('pitch', 'PitchAxis')):
            a = m.get(axis)
            if isinstance(a, dict) and key not in out:
                out[key] = _num(a.get('Speed'))
                lim = [x for x in a.get('AngleLimits') or [] if isinstance(x, dict)]
                if lim:
                    out[f'{key}_limit'] = [_num(lim[0].get('LowestAngle')), _num(lim[0].get('HighestAngle'))]
    return out


def _stats_of(item_type: str, std: dict) -> dict:
    if item_type in ('WeaponGun', 'WeaponMining') and isinstance(std.get('Weapon'), dict):
        out = _weapon_stats(std)
        ml = std.get('MiningLaser') if isinstance(std.get('MiningLaser'), dict) else None
        if ml:
            out.update({'mining_power': _num(ml.get('PowerTransfer')), 'mining_min_power': _num(ml.get('MinPowerTransfer')),
                        'optimal_range': _num(ml.get('OptimalRange')), 'max_range': _num(ml.get('MaximumRange')),
                        'module_slots': _num(ml.get('ModuleSlots'))})
        return out
    if item_type in ('Missile', 'Bomb'):
        m = std.get('Missile') if isinstance(std.get('Missile'), dict) else {}
        tgt = m.get('Targeting') if isinstance(m.get('Targeting'), dict) else {}
        gcs = m.get('GCS') if isinstance(m.get('GCS'), dict) else {}
        return {'damage_total': _num(m.get('DamageTotal'), 0), 'damage': _dmg(m.get('Damage')),
                'tracking': tgt.get('TrackingSignalType'), 'lock_time': _num(tgt.get('LockTime')),
                'lock_angle': _num(tgt.get('LockingAngle')),
                'lock_range': [_num(tgt.get('LockRangeMin')), _num(tgt.get('LockRangeMax'))],
                'speed': _num(gcs.get('LinearSpeed')), 'distance': _num(m.get('Distance'))}
    if item_type in ('MissileLauncher', 'BombLauncher'):
        r = std.get('MissileRack') if isinstance(std.get('MissileRack'), dict) else {}
        return {'count': _num(r.get('MissileCount')), 'missile_size': _num(r.get('MissileSize'))}
    if item_type == 'Shield':
        s = std.get('Shield') if isinstance(std.get('Shield'), dict) else {}
        return {'hp': _num(s.get('MaxShieldHealth'), 0), 'regen': _num(s.get('MaxShieldRegen'), 0),
                'damaged_delay': _num(s.get('DamagedDelay')), 'downed_delay': _num(s.get('DownedDelay')),
                'absorption': _range_map(s.get('Absorption')), 'resistance': _range_map(s.get('Resistance'))}
    if item_type == 'QuantumDrive':
        q = std.get('QuantumDrive') if isinstance(std.get('QuantumDrive'), dict) else {}
        j = q.get('StandardJump') if isinstance(q.get('StandardJump'), dict) else {}
        sp = q.get('SplineJump') if isinstance(q.get('SplineJump'), dict) else {}
        return {'speed': _num(j.get('DriveSpeed')), 'spool': _num(j.get('SpoolUpTime')),
                'cooldown': _num(j.get('CooldownTime')), 'fuel_req': _num(q.get('QuantumFuelRequirement')),
                'stage1_accel': _num(j.get('StageOneAccelRate')), 'stage2_accel': _num(j.get('StageTwoAccelRate')),
                'spline_speed': _num(sp.get('DriveSpeed'))}
    if item_type == 'JumpDrive':
        j = std.get('JumpDrive') if isinstance(std.get('JumpDrive'), dict) else {}
        return {'align': _num(j.get('AlignmentRate')), 'tune': _num(j.get('TuningRate')),
                'fuel_eff': _num(j.get('FuelUsageEfficiencyMultiplier'))}
    if item_type == 'Radar':
        r = std.get('Radar') if isinstance(std.get('Radar'), dict) else {}
        sens = r.get('Sensitivity') if isinstance(r.get('Sensitivity'), dict) else {}
        return {'sensitivity': {k.lower(): v for k, v in sens.items() if k in ('IR', 'EM', 'CS', 'RS')},
                'cooldown': _num(r.get('Cooldown'))}
    if item_type == 'WeaponDefensive':
        d = std.get('WeaponDefensive') if isinstance(std.get('WeaponDefensive'), dict) else {}
        return {'cm_type': d.get('Type'), 'ammo': _num(d.get('Capacity'))}
    if item_type in ('Turret', 'TurretBase'):
        return _turret_stats(std)
    return {}


def _resource_stats(std: dict) -> dict:
    """發電、冷卻、耗電、耗冷卻、訊號（每個配件都有的部分）。"""
    rn = std.get('ResourceNetwork') if isinstance(std.get('ResourceNetwork'), dict) else {}
    gen = rn.get('Generation') if isinstance(rn.get('Generation'), dict) else {}
    usage = rn.get('Usage') if isinstance(rn.get('Usage'), dict) else {}
    pw = usage.get('Power') if isinstance(usage.get('Power'), dict) else {}
    cl = usage.get('Coolant') if isinstance(usage.get('Coolant'), dict) else {}
    em = (std.get('Emission') or {}).get('Em') if isinstance(std.get('Emission'), dict) else None
    # 電源分段的效能倍率：分到 Start 格以上就用那一段的 Modifier（例如護盾 1 格 0.7、3 格 0.85、5 格 1）
    states = [s for s in rn.get('States') or [] if isinstance(s, dict)]
    ranges = [[_num(r.get('Start'), 0), _num(r.get('Modifier'), 1)]
              for r in (states[0].get('PowerRanges') or [] if states else []) if isinstance(r, dict)]
    out = {
        'power_ranges': ranges if any(m != 1 for _, m in ranges) else None,
        'power_gen': _num(gen.get('Power')), 'coolant_gen': _num(gen.get('Coolant')),
        'power_use': [_num(pw.get('Minimum')), _num(pw.get('Maximum'))] if pw else None,
        'coolant_use': [_num(cl.get('Minimum')), _num(cl.get('Maximum'))] if cl else None,
        'em': _num(em.get('Maximum')) if isinstance(em, dict) else None,
        'ir': _num((std.get('Emission') or {}).get('Ir')) if isinstance(std.get('Emission'), dict) else None,
    }
    return {k: v for k, v in out.items() if v not in (None, 0)}


def _item_class(std: dict) -> Optional[str]:
    data = std.get('DescriptionData') if isinstance(std.get('DescriptionData'), dict) else {}
    value = data.get('Class')
    return value.strip() if isinstance(value, str) and value.strip() else None


def item_ports(ports) -> list:
    """配件本身的子槽（砲塔的武器槽、飛彈架的飛彈槽…）；武器配件槽（WeaponAttachment）不列。"""
    out = []
    for p in ports or []:
        if not isinstance(p, dict) or not p.get('PortName'):
            continue
        types = compat_types(p)
        if not types or not any(_base(t) in LOADOUT_TYPES for t in types):
            continue
        out.append({'port': p['PortName'], 'types': types,
                    'min': _num(p.get('MinSize'), _num(p.get('Size'), 0)),
                    'max': _num(p.get('MaxSize'), _num(p.get('Size'), 0)),
                    'editable': not p.get('Uneditable'),
                    'default': p.get('EquippedItem') or None})
    return out


def map_ship_item(row: dict) -> Optional[dict]:
    std = row.get('stdItem') if isinstance(row.get('stdItem'), dict) else {}
    uuid = std.get('UUID') or row.get('reference')
    item_type = row.get('type') or ''
    class_name = row.get('className') or std.get('ClassName') or ''
    name = _real_name(row.get('name') or std.get('Name'))
    if not uuid or item_type not in LOADOUT_TYPES or not name or class_name.lower().startswith('test_'):
        return None
    mfr = std.get('Manufacturer') if isinstance(std.get('Manufacturer'), dict) else {}
    grade = std.get('Grade')
    return {
        '_id': uuid,
        'class_name': class_name,
        'name': name,
        'name_lower': name.lower(),
        'name_zh': item_name_zh(name, class_name),
        'type': item_type,
        'sub_type': row.get('subType') or '',
        'size': _num(row.get('size'), _num(std.get('Size'), 0)),
        'grade': 'ABCDEFG'[grade - 1] if isinstance(grade, int) and 1 <= grade <= 7 else None,
        'item_class': _item_class(std),
        'manufacturer': mfr.get('Code') or row.get('manufacturer'),
        'manufacturer_name': mfr.get('Name'),
        'tags': [t for t in std.get('Tags') or [] if isinstance(t, str)],
        'required_tags': [t for t in std.get('RequiredTags') or [] if isinstance(t, str)],
        'mass': _num(std.get('Mass')),
        'hp': _num((std.get('Durability') or {}).get('Health')) if isinstance(std.get('Durability'), dict) else None,
        'ports': item_ports(std.get('Ports')),
        'stats': {**_resource_stats(std), **_stats_of(item_type, std)},
    }


# ─────────────────────────────────────────── ships.json

def _slot(node: dict, parent_id: str) -> Optional[dict]:
    """掛點樹的一格；跟配裝無關的（門、螢幕、座位、燃料、推進器…）回 None。"""
    port = node.get('HardpointName') or ''
    if not port:
        return None
    types = compat_types(node)
    if not types and node.get('Type'):
        types = [node['Type'].replace('.UNDEFINED', '')]
    if not any(_base(t) in LOADOUT_TYPES for t in types):
        return None
    slot_id = f'{parent_id}/{port}' if parent_id else port
    children = [c for c in (_slot(ch, slot_id) for ch in node.get('Loadout') or [] if isinstance(ch, dict)) if c]
    item = node.get('UUID') if node.get('ClassName') else None
    editable = bool(node.get('Editable'))
    # 鎖死又沒有子槽的砲塔外殼（例如只有攝影機的魚雷瞄準塔）沒東西可看
    if not editable and not children and _base(node.get('Type') or '') in ('Turret', 'TurretBase') \
            and not node.get('Weapons'):
        return None
    out = {'id': slot_id, 'port': port, 'types': types,
           'min': _num(node.get('MinSize'), 0), 'max': _num(node.get('MaxSize'), 0),
           'editable': editable, 'item': item, 'children': children}
    # 配件主檔沒有的（例如船專屬的飛彈架、有人砲塔底座）前端就顯示這兩個
    if node.get('ClassName'):
        out['item_class_name'] = node['ClassName']
    name = _real_name(node.get('Name'))
    if name:
        out['name'] = name
    if node.get('IsPilotSlaveable'):
        out['slaveable'] = True          # 遙控砲塔：駕駛可以連動開火
    if node.get('PortTags'):
        out['tags'] = [t for t in node['PortTags'] if isinstance(t, str)]
    return out


def _walk_tags(nodes, port_scoped: set, required: set):
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        port_scoped.update(t.lower() for t in n.get('PortTags') or [] if isinstance(t, str))
        required.update(t.lower() for t in n.get('RequiredTags') or [] if isinstance(t, str))
        _walk_tags(n.get('Loadout'), port_scoped, required)


def ship_tags(doc: dict) -> list:
    """船本身提供的標籤：船的 PortTags＋預設配備用到的 RequiredTags（預設配備一定合法，表示船有這些標籤），
    只在某個槽才有的標籤（例如 PDC）不算，交給那個槽的 tags。"""
    port_scoped, required = set(), set()
    _walk_tags(doc.get('Loadout'), port_scoped, required)
    own = {t.lower() for t in doc.get('PortTags') or [] if isinstance(t, str)}
    return sorted(own | (required - port_scoped))



def _power(doc: dict) -> Optional[dict]:
    """電源與訊號計算要的船層級資料（見 frontend/src/utils/loadoutPower.js）：
    發電格數（預設發電機）、武器電源池大小、各類耗電者的預設值（耗電、EM、冷卻）、
    裝甲的訊號倍率，以及資料集算好的預設訊號（對照用）。"""
    pw = doc.get('Power') if isinstance(doc.get('Power'), dict) else {}
    if not pw.get('GenerationSegments'):
        return None
    em = doc.get('Emission') if isinstance(doc.get('Emission'), dict) else {}
    cool = doc.get('Cooling') if isinstance(doc.get('Cooling'), dict) else {}
    pools = doc.get('PowerPools') if isinstance(doc.get('PowerPools'), dict) else {}
    sm = ((doc.get('Armor') or {}).get('SignalMultipliers') or {}) if isinstance(doc.get('Armor'), dict) else {}
    max_seg = pw.get('MaxSegments') if isinstance(pw.get('MaxSegments'), dict) else {}
    used_seg = pw.get('UsedSegmentsGrouped') if isinstance(pw.get('UsedSegmentsGrouped'), dict) else {}
    em_groups = em.get('EmGroupsShields') if isinstance(em.get('EmGroupsShields'), dict) else {}
    cool_groups = cool.get('UsedSegmentsShieldsGrouped') if isinstance(cool.get('UsedSegmentsShieldsGrouped'), dict) else {}
    # 每一類耗電者的預設值（耗電、EM、耗冷卻）；前端（loadoutPower.js 的 MODELED）以外的當成固定耗電者，
    # 有建模的類別如果掛點樹裡找不到（例如配件主檔沒收）也用這裡的值補
    groups = {}
    for group in set(used_seg) | set(em_groups) | set(cool_groups):
        if group == 'PowerPlant':
            continue
        power = _num(used_seg.get(group), 0) or _num(max_seg.get(group), 0)
        groups[group] = {'power': power, 'em': _num(em_groups.get(group), 0), 'coolant': _num(cool_groups.get(group), 0)}
    pool = lambda k: _num((pools.get(k) or {}).get('Size')) if isinstance(pools.get(k), dict) else None
    return {
        'gen': _num(pw.get('GenerationSegments')),
        'weapon_pool': pool('WeaponGun'),
        'groups': groups,
        'signal': {'em': _num(sm.get('Electromagnetic'), 1), 'ir': _num(sm.get('Infrared'), 1),
                   'cs': _num(sm.get('CrossSection'), 1)},
        'baseline': {'used': _num(pw.get('UsedSegmentsShields')), 'em': _num(em.get('EmShields')),
                     'ir': _num(em.get('IrShields')), 'em_quantum': _num(em.get('EmQuantum')),
                     'ir_quantum': _num(em.get('IrQuantum')), 'coolant_gen': _num(cool.get('GenerationSegments'))},
    }


def map_ship_loadout(doc: dict) -> Optional[dict]:
    uuid = doc.get('UUID')
    name = _real_name(doc.get('Name'))
    if not uuid or not name or doc.get('IsPowerSuit'):
        return None
    slots = [s for s in (_slot(n, '') for n in doc.get('Loadout') or [] if isinstance(n, dict)) if s]
    if not slots:
        return None
    class_name = doc.get('ClassName') or ''
    armor = doc.get('Armor') if isinstance(doc.get('Armor'), dict) else {}
    mult = armor.get('DamageMultipliers') if isinstance(armor.get('DamageMultipliers'), dict) else {}
    pen_res = armor.get('PenetrationResistance') if isinstance(armor.get('PenetrationResistance'), dict) else {}
    pen_mult = doc.get('PenetrationMultiplier') if isinstance(doc.get('PenetrationMultiplier'), dict) else {}
    ifcs = ((doc.get('FlightCharacteristics') or {}).get('IFCS') or {}) \
        if isinstance(doc.get('FlightCharacteristics'), dict) else {}
    agility = doc.get('Agility') if isinstance(doc.get('Agility'), dict) else {}
    accel = agility.get('Acceleration') if isinstance(agility.get('Acceleration'), dict) else {}
    qt = doc.get('QuantumTravel') if isinstance(doc.get('QuantumTravel'), dict) else {}
    prop = doc.get('Propulsion') if isinstance(doc.get('Propulsion'), dict) else {}
    mfr = doc.get('Manufacturer') if isinstance(doc.get('Manufacturer'), dict) else {}
    cs = doc.get('CrossSection') if isinstance(doc.get('CrossSection'), dict) else {}
    weaponry = doc.get('Weaponry') if isinstance(doc.get('Weaponry'), dict) else {}
    sc = doc.get('ShieldController') if isinstance(doc.get('ShieldController'), dict) else {}
    parts = [{'name': p.get('Name'), 'hp': _num(p.get('HP'))}
             for p in doc.get('DamageBeforeDestruction') or [] if isinstance(p, dict) and _num(p.get('HP'))]
    return {
        '_id': uuid,
        'class_name': class_name,
        'name': name,
        'name_lower': name.lower(),
        'name_zh': vehicle_name_zh(class_name, name),
        'manufacturer': mfr.get('Code'),
        'manufacturer_name': mfr.get('Name'),
        'size': _num(doc.get('Size')),
        'career': doc.get('Career'),
        'role': doc.get('Role'),
        'role_zh': vehicle_role_zh(doc.get('Role') or ''),
        'crew': _num(doc.get('Crew')),
        'is_spaceship': bool(doc.get('IsSpaceship')),
        'dimensions': [_num(doc.get('Length')), _num(doc.get('Width')), _num(doc.get('Height'))],
        'mass': _num(doc.get('MassTotal'), _num(doc.get('Mass'))),
        'cargo': _num(doc.get('Cargo')),
        'hull': {
            'hp': _num(doc.get('Health')),
            'parts': parts,
            'armor_hp': _num(armor.get('Health')),
            # 裝甲受到的傷害倍率（< 1 ＝ 減傷）、抗性倍率、偏轉門檻（低於這個傷害的子彈被彈開）
            'armor_damage': {k.lower(): mult[k] for k in DAMAGE_KEYS if _num(mult.get(k)) is not None},
            'armor_resist': {k.lower(): v for k, v in (armor.get('ResistanceMultipliers') or {}).items()
                             if k in DAMAGE_KEYS and _num(v) is not None},
            'deflection': _dmg(armor.get('Deflection')),
            'pen_resist': {k.lower(): v for k, v in pen_res.items() if _num(v) is not None},
            # 穿透倍率：Fuse（打穿裝甲後對內部保險絲）、Components（對內部配件）
            'pen_multiplier': {k.lower(): v for k, v in pen_mult.items() if _num(v) is not None},
        },
        'shield_face': sc.get('FaceType'),
        # 同時運作的護盾數（PowerPools.Shield.Size；比護盾槽少的船，多出來的是備用）
        'shield_slots': _num(((doc.get('PowerPools') or {}).get('Shield') or {}).get('Size'))
        if isinstance(doc.get('PowerPools'), dict) else None,
        'cross_section': [_num(cs.get('X')), _num(cs.get('Y')), _num(cs.get('Z'))],
        'distortion_pool': _num((doc.get('Distortion') or {}).get('Pool')) if isinstance(doc.get('Distortion'), dict) else None,
        'flight': {
            'scm': _num(ifcs.get('ScmSpeed')), 'boost_forward': _num(ifcs.get('BoostSpeedForward')),
            'boost_backward': _num(ifcs.get('BoostSpeedBackward')), 'max': _num(ifcs.get('MaxSpeed')),
            'pitch': _num(agility.get('Pitch')), 'yaw': _num(agility.get('Yaw')), 'roll': _num(agility.get('Roll')),
            'pitch_boost': _num(agility.get('PitchBoosted')), 'yaw_boost': _num(agility.get('YawBoosted')),
            'roll_boost': _num(agility.get('RollBoosted')),
            'accel_main': _num(accel.get('Main')), 'accel_retro': _num(accel.get('Retro')),
            'accel_maneuver': _num(accel.get('Maneuver')),
        },
        'fuel': {'hydrogen': _num(prop.get('FuelCapacity')), 'quantum': _num(qt.get('FuelCapacity'))},
        # 預設配備的武器總數值（對照用）
        'baseline': {'pilot_dps': _num(weaponry.get('PilotDps')), 'pilot_alpha': _num(weaponry.get('PilotAlpha')),
                     'turret_dps': _num(weaponry.get('TurretDps')), 'missiles': _num(weaponry.get('TotalMissiles')),
                     'shield_hp': _num(doc.get('ShieldHp')), 'qt_range': _num(qt.get('Range'))},
        'power': _power(doc),
        'tags': ship_tags(doc),
        'slots': slots,
    }
