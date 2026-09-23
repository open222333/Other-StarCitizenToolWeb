"""VehicleMaster（艦船主檔）查詢／篩選／排序的測試。

管理後台新增「艦船基本資料」列表頁，照全站搜尋優化計畫（藍圖登記管理
那批）的既有做法：多選篩選 + 白名單排序 + 分頁。這支測試鎖住
VehicleMaster.list_all()／count() 的篩選條件組合行為，避免以後改壞。
"""
import pytest

from src.models.item import VehicleMaster


@pytest.fixture
def seeded_vehicles():
    """4 艘船，涵蓋不同 career／role／manufacturer_code／size_class，
    足以驗證多選篩選跟排序。"""
    col = VehicleMaster._col()
    col.insert_many([
        {'_id': 'v-aurora', 'name': 'Aurora MR', 'name_lower': 'aurora mr',
         'career': 'Starter', 'role': 'Starter / Light Fighter',
         'manufacturer_code': 'RSI', 'manufacturer_name': 'Roberts Space Industries',
         'size_class': 1, 'crew_max': 1, 'cargo_capacity_scu': 4,
         'mass_hull': 63000, 'msrp': 3500000, 'is_current': True},
        {'_id': 'v-freelancer', 'name': 'Freelancer', 'name_lower': 'freelancer',
         'career': 'Transport', 'role': 'Light Freight',
         'manufacturer_code': 'MISC', 'manufacturer_name': 'Musashi Industrial and Starflight Concern',
         'size_class': 3, 'crew_max': 4, 'cargo_capacity_scu': 66,
         'mass_hull': 132000, 'msrp': 11500000, 'is_current': True},
        {'_id': 'v-hornet', 'name': 'F7C Hornet', 'name_lower': 'f7c hornet',
         'career': 'Combat', 'role': 'Light Fighter',
         'manufacturer_code': 'AEGS', 'manufacturer_name': 'Aegis Dynamics',
         'size_class': 2, 'crew_max': 1, 'cargo_capacity_scu': 0,
         'mass_hull': 45000, 'msrp': 7500000, 'is_current': True},
        {'_id': 'v-retired', 'name': 'Old Ship', 'name_lower': 'old ship',
         'career': 'Combat', 'role': 'Light Fighter',
         'manufacturer_code': 'AEGS', 'manufacturer_name': 'Aegis Dynamics',
         'size_class': 1, 'crew_max': 1, 'cargo_capacity_scu': 0,
         'mass_hull': 40000, 'msrp': 1, 'is_current': False},
    ])
    yield


def test_list_all_excludes_non_current(seeded_vehicles):
    rows, total = VehicleMaster.list_all()
    assert total == 3
    assert 'v-retired' not in {r['_id'] for r in rows}


def test_list_all_filters_by_career(seeded_vehicles):
    rows, total = VehicleMaster.list_all(careers=['Combat'])
    assert total == 1
    assert rows[0]['_id'] == 'v-hornet'


def test_list_all_filters_by_multiple_careers(seeded_vehicles):
    rows, total = VehicleMaster.list_all(careers=['Combat', 'Starter'])
    assert total == 2
    assert {r['_id'] for r in rows} == {'v-hornet', 'v-aurora'}


def test_list_all_filters_by_manufacturer_code(seeded_vehicles):
    rows, total = VehicleMaster.list_all(manufacturer_codes=['MISC'])
    assert total == 1
    assert rows[0]['_id'] == 'v-freelancer'


def test_list_all_filters_by_size_class(seeded_vehicles):
    """size_class 存數字，query string 進來的多選值是字串，要能正確轉型比對。"""
    rows, total = VehicleMaster.list_all(size_classes=['1'])
    assert total == 1
    assert rows[0]['_id'] == 'v-aurora'


def test_list_all_ignores_invalid_size_class_value(seeded_vehicles):
    """size_class 帶進來一個轉不了 int 的值，不能讓整個查詢 500，直接忽略它。"""
    rows, total = VehicleMaster.list_all(size_classes=['not-a-number'])
    # 無效值被濾掉後等於沒有 size_class 篩選，回全部 is_current 的船
    assert total == 3


def test_list_all_name_query_filter(seeded_vehicles):
    rows, total = VehicleMaster.list_all(query='hornet')
    assert total == 1
    assert rows[0]['_id'] == 'v-hornet'


def test_list_all_sorts_by_cargo_capacity(seeded_vehicles):
    rows, _ = VehicleMaster.list_all(sort_by='cargo_capacity_scu', sort_dir=-1)
    assert rows[0]['_id'] == 'v-freelancer'  # 66 SCU 最大


def test_list_all_invalid_sort_by_falls_back_to_name(seeded_vehicles):
    rows, _ = VehicleMaster.list_all(sort_by='raw', sort_dir=1)
    # 字母序：Aurora MR < F7C Hornet < Freelancer（'7' 的 ASCII 比 'r' 小）
    assert [r['_id'] for r in rows] == ['v-aurora', 'v-hornet', 'v-freelancer']


def test_count_matches_list_all_filters(seeded_vehicles):
    assert VehicleMaster.count(careers=['Combat']) == 1
    assert VehicleMaster.count() == 3


def test_careers_lists_distinct_current_only(seeded_vehicles):
    assert VehicleMaster.careers() == ['Combat', 'Starter', 'Transport']


def test_roles_lists_distinct_current_only(seeded_vehicles):
    assert set(VehicleMaster.roles()) == {
        'Light Fighter', 'Light Freight', 'Starter / Light Fighter'}


def test_size_classes_lists_distinct_current_only(seeded_vehicles):
    assert VehicleMaster.size_classes() == [1, 2, 3]


def test_manufacturers_returns_code_and_label(seeded_vehicles):
    rows = VehicleMaster.manufacturers()
    by_code = {r['value']: r['label'] for r in rows}
    assert by_code == {
        'RSI': 'Roberts Space Industries',
        'MISC': 'Musashi Industrial and Starflight Concern',
        'AEGS': 'Aegis Dynamics',
    }
