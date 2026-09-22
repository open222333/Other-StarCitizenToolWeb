"""src/sc_zh.py 對照表快取的行為測試。

重點測試「改了 JSON 檔會不會被讀到」——這幾份表原本是 process 生命週期只讀
一次的全域快取，改完 JSON 檔如果 worker/api container 沒重啟就吃不到新值，
容易讓人誤以為改動沒生效（實際發生過一次：mining 對照表改用翻譯包來源後，
同步跑完中文譯名還是舊的，最後才發現是 worker container 沒重啟、記憶體裡
還是舊版快取）。改成用 mtime 判斷是否要重讀之後，不用重啟 process 也能拿到
新值，這裡鎖住這個行為，以免以後又被改回「只讀一次」的寫法。
"""
import importlib
import json
import os

import pytest

import src.sc_zh as sc_zh


@pytest.fixture(autouse=True)
def _reset_cache():
    """避免這支測試檔的多個測試互相汙染快取，也避免污染其他測試檔。"""
    importlib.reload(sc_zh)
    yield
    importlib.reload(sc_zh)


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def test_mining_resource_name_zh_picks_up_file_change_without_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(sc_zh, '_DATA_DIR', tmp_path)
    path = tmp_path / 'sc_mining_resource_names_zh.json'

    _write_json(path, {'Ore_Aluminum': '舊譯名'})
    mtime1 = path.stat().st_mtime
    assert sc_zh.mining_resource_name_zh('Ore_Aluminum') == '舊譯名'

    _write_json(path, {'Ore_Aluminum': '新譯名'})
    # 有些檔案系統 mtime 精度只到秒，測試環境跑太快可能兩次寫入 mtime 一樣，
    # 這裡強制往前推 2 秒確保一定偵測得到差異，不受測試執行速度影響。
    os.utime(path, (mtime1 + 2, mtime1 + 2))

    assert sc_zh.mining_resource_name_zh('Ore_Aluminum') == '新譯名'


def test_lookup_is_cached_when_file_unchanged(tmp_path, monkeypatch):
    """檔案沒變的情況下不該每次呼叫都重新開檔重讀（避免退化成每次都 I/O）。"""
    monkeypatch.setattr(sc_zh, '_DATA_DIR', tmp_path)
    path = tmp_path / 'sc_item_names_zh.json'
    _write_json(path, {'Aluminum': '鋁'})

    calls = []
    real_open = open

    def counting_open(file, *args, **kwargs):
        calls.append(file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr('builtins.open', counting_open)

    sc_zh.item_name_zh('Aluminum')
    sc_zh.item_name_zh('Aluminum')
    sc_zh.item_name_zh('Aluminum')

    assert len(calls) == 1, f'檔案沒變卻重讀了 {len(calls)} 次，快取沒生效'


def test_missing_file_returns_none_and_recovers_once_created(tmp_path, monkeypatch):
    """檔案還不存在時查不到回傳 None（不炸），檔案之後被建立也要能讀到。"""
    monkeypatch.setattr(sc_zh, '_DATA_DIR', tmp_path)
    assert sc_zh.location_name_zh('Somewhere') is None

    path = tmp_path / 'sc_location_names_zh.json'
    _write_json(path, {'Somewhere': '某處'})
    assert sc_zh.location_name_zh('Somewhere') == '某處'


def test_mining_deposit_name_zh_looks_up_its_own_file(tmp_path, monkeypatch):
    """礦床名稱表跟礦物商品表是分開的兩個檔案，不能互相串到對方的資料。"""
    monkeypatch.setattr(sc_zh, '_DATA_DIR', tmp_path)
    _write_json(tmp_path / 'sc_mining_resource_names_zh.json', {'Ore_Aluminum': '鋁礦石'})
    _write_json(tmp_path / 'sc_mining_deposit_names_zh.json', {'Granite Deposit': '花崗岩礦床'})

    assert sc_zh.mining_resource_name_zh('Ore_Aluminum') == '鋁礦石'
    assert sc_zh.mining_deposit_name_zh('Granite Deposit') == '花崗岩礦床'
    # 兩份表是分開的 key 空間，查另一份表沒有的 key 要是 None，不能互相污染。
    assert sc_zh.mining_deposit_name_zh('Ore_Aluminum') is None
    assert sc_zh.mining_resource_name_zh('Granite Deposit') is None
