"""礦物回波參考查詢（唯讀）。

資料由 tasks/scdata_sync.py 從 scunpacked-data 同步而來，本藍圖只讀不寫。
這是靜態的礦床成分/機率參考表，不是玩家實際掃描到的即時回波數值——
詳見 src/models/mining.py 檔頭說明。

資料量小（約 270 個礦床、60 個地點群組），不分頁，一次回全部由前端篩選排序，
比照 /user/templates/ 的作法。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.permissions import READ_ROLES, WRITE_ROLES, admin_api, viewer_sees_hidden

from src.models.log import Log
from src.models.mining import MiningDeposit, MiningLocation
from src.models.uex_commodity import UexCommodity
from src.models.uex_commodity_price import UexCommodityPrice

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
    return jsonify({'success': True, 'data': MiningDeposit.list_all(visible_only=not viewer_sees_hidden())})


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
    return jsonify({'success': True, 'data': MiningLocation.list_all(visible_only=not viewer_sees_hidden())})


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


@app_mining.route('/uex-commodities', methods=['GET'])
@admin_api(*READ_ROLES)
def list_uex_commodities():
    """UEX 商品清單（代碼、名稱），給後台礦物資料庫手動指定關聯用。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{id, code, name, kind, is_raw}]"
    """
    return jsonify({'success': True, 'data': UexCommodity.list_all()})


@app_mining.route('/uex-commodities/detail', methods=['GET'])
@admin_api(*READ_ROLES)
def list_uex_commodities_detail():
    """後台「商品資料庫」：全部 UEX 商品（縮寫、名稱、類別、參考價、屬性）＋關聯到的礦物。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{id, code, name, kind, weight_scu, price_buy, price_sell, is_*…, minerals: [...]}]"
    """
    return jsonify({'success': True, 'data': UexCommodity.list_detail()})


@app_mining.route('/uex-commodity-prices', methods=['GET'])
@admin_api(*READ_ROLES)
def list_uex_commodity_prices():
    """後台「商品資料庫 › 商品價格」：UEX 商品在各交易終端的買賣價（uex_commodities_prices），分頁。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q, type: string, description: "商品縮寫／名稱、終端名稱"}
      - {in: query, name: commodity, type: string, description: "UEX 商品 id"}
      - {in: query, name: star_system, type: string}
      - {in: query, name: side, type: string, description: "buy＝只看買得到的、sell＝只看能賣的"}
      - {in: query, name: limit, type: integer, default: 50}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: "data: [{id, commodity, terminal, price_buy, scu_buy, price_sell, …, date_modified}]、total"
    """
    args = request.args
    try:
        limit = int(args.get('limit') or 50)
        offset = int(args.get('offset') or 0)
    except ValueError:
        return jsonify({'success': False, 'message': 'limit／offset 必須是整數'}), 400
    rows, total = UexCommodityPrice.admin_list(
        q=args.get('q') or '', commodity=args.get('commodity') or '',
        star_system=args.get('star_system') or '', side=args.get('side') or '',
        limit=limit, offset=offset)
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'star_systems': UexCommodityPrice.star_systems()})


@app_mining.route('/uex-terminals', methods=['GET'])
@admin_api(*READ_ROLES)
def list_uex_terminals():
    """後台「商品資料庫 › 交易終端」：UEX 交易終端（uex_terminals）全部，附可買／可賣的商品數。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{id, name, code, type, location, star_system_name, …, commodity_buy_count, commodity_sell_count}]"
    """
    return jsonify({'success': True, 'data': UexCommodityPrice.admin_terminals()})


@app_mining.route('/minerals/<path:resource_key>/uex', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def set_mineral_uex(resource_key):
    """手動指定礦物對應的 UEX 商品（自動比對對不到或對錯時用）。
    ---
    tags: [Mining]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: resource_key, type: string, required: true}
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            uex_id: {type: string, description: "UEX 商品 id；空字串 = 不關聯；null = 改回自動比對"}
    responses:
      200:
        description: 成功
      400:
        description: 找不到這個 UEX 商品
    """
    data = request.get_json(silent=True) or {}
    if 'uex_id' not in data:
        return jsonify({'success': False, 'message': '沒有要更新的 uex_id'}), 400
    try:
        UexCommodity.set_link(resource_key, data.get('uex_id'), updated_by=get_jwt_identity())
    except ValueError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(get_jwt_identity(), 'set_mineral_uex', f'礦物 {resource_key} 的 UEX 商品：{data.get("uex_id")}')
    return jsonify({'success': True})
