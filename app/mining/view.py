"""礦物回波參考查詢（唯讀）。

資料由 tasks/scdata_sync.py 從 scunpacked-data 同步而來，本藍圖只讀不寫。
這是靜態的礦床成分/機率參考表，不是玩家實際掃描到的即時回波數值——
詳見 src/models/mining.py 檔頭說明。

資料量小（約 270 個礦床、60 個地點群組），不分頁，一次回全部由前端篩選排序，
比照 /user/templates/ 的作法。
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from src.models.mining import MiningDeposit, MiningLocation

app_mining = Blueprint('app_mining', __name__)


@app_mining.route('/deposits', methods=['GET'])
@jwt_required()
def list_deposits():
    """礦床成分機率參考表（全部，不分頁）。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': MiningDeposit.list_all()})


@app_mining.route('/locations', methods=['GET'])
@jwt_required()
def list_locations():
    """星系/地點的礦床出現機率參考表（全部，不分頁）。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': MiningLocation.list_all()})


@app_mining.route('/systems', methods=['GET'])
@jwt_required()
def list_systems():
    """所有出現過的星系名稱（給地點篩選下拉選單用）。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': MiningLocation.systems()})
