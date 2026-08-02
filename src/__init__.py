from configparser import ConfigParser
from os.path import exists, join
from os import makedirs, environ
import logging


config = ConfigParser()
config.read(join('conf', 'config.ini'))


# logs相關參數
# 關閉log功能 輸入選項 (true, True, 1) 預設 不關閉
LOG_DISABLE = config.getboolean('LOG', 'LOG_DISABLE', fallback=False)
# logs路徑 預設 logs
LOG_PATH = config.get('LOG', 'LOG_PATH', fallback='logs')
# 設定紀錄log等級 DEBUG,INFO,WARNING,ERROR,CRITICAL 預設WARNING
LOG_LEVEL = config.get('LOG', 'LOG_LEVEL', fallback='WARNING')
# 關閉紀錄log檔案 輸入選項 (true, True, 1)  預設 不關閉
LOG_FILE_DISABLE = config.getboolean('LOG', 'LOG_FILE_DISABLE', fallback=False)

# 建立log資料夾
if not exists(LOG_PATH) and not LOG_DISABLE:
    makedirs(LOG_PATH)

if LOG_DISABLE:
    logging.disable()


# flask json 設定檔路徑 預設值 conf/flask.json
FLASK_JSON_PATH = config.get('SETTING', 'FLASK_JSON_PATH', fallback=join('conf', 'flask.json'))

# 後台管理頁面名稱 預設值 後台管理
ADMIN_TITLE = config.get('SETTING', 'ADMIN_TITLE', fallback='後台管理')

# Flask 參數
FLASK_PORT = int(environ.get('FLASK_PORT', 5000))
JWT_ACCESS_TOKEN_EXPIRES_HOURS = int(environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS', 8))
JWT_REFRESH_TOKEN_EXPIRES_DAYS = int(environ.get('JWT_REFRESH_TOKEN_EXPIRES_DAYS', 30))

# MongoDB 連線參數
MONGO_URI = config.get('MONGO', 'MONGO_URI', fallback='mongodb://localhost:27017')
MONGO_DB = config.get('MONGO', 'MONGO_DB', fallback='flask_app')

# MySQL 連線參數
MYSQL_HOST = config.get('MYSQL', 'MYSQL_HOST', fallback='localhost')
MYSQL_PORT = config.getint('MYSQL', 'MYSQL_PORT', fallback=3306)
MYSQL_USER = config.get('MYSQL', 'MYSQL_USER', fallback='root')
MYSQL_PASSWORD = config.get('MYSQL', 'MYSQL_PASSWORD', fallback='')
MYSQL_DB = config.get('MYSQL', 'MYSQL_DB', fallback='flask_app')

# Redis 連線參數
REDIS_HOST = config.get('REDIS', 'REDIS_HOST', fallback='localhost')
REDIS_PORT = config.getint('REDIS', 'REDIS_PORT', fallback=6379)
REDIS_PASSWORD = config.get('REDIS', 'REDIS_PASSWORD', fallback='')
REDIS_DB = config.getint('REDIS', 'REDIS_DB', fallback=0)

# 星際公民遊戲資料來源參數（社群 API，非官方）
SCDATA_WIKI_API_BASE = config.get(
    'SCDATA', 'WIKI_API_BASE', fallback='https://api.star-citizen.wiki/api').rstrip('/')
SCDATA_UEX_API_BASE = config.get(
    'SCDATA', 'UEX_API_BASE', fallback='https://api.uexcorp.uk/2.0').rstrip('/')
# 每次請求間隔秒數，別把社群自費維運的 API 打爆
SCDATA_REQUEST_DELAY = config.getfloat('SCDATA', 'REQUEST_DELAY', fallback=0.25)
SCDATA_HTTP_TIMEOUT = config.getfloat('SCDATA', 'HTTP_TIMEOUT', fallback=60)
SCDATA_MAX_RETRIES = config.getint('SCDATA', 'MAX_RETRIES', fallback=5)
SCDATA_BULK_SIZE = config.getint('SCDATA', 'BULK_SIZE', fallback=500)
# vehicles 單筆 payload 約 40KB，page size 要開小
SCDATA_PAGE_SIZES = {
    'items': config.getint('SCDATA', 'PAGE_SIZE_ITEMS', fallback=100),
    'vehicles': config.getint('SCDATA', 'PAGE_SIZE_VEHICLES', fallback=5),
    'commodities': config.getint('SCDATA', 'PAGE_SIZE_COMMODITIES', fallback=100),
}
# CIG 要求標示非官方；也讓 API 維運者知道流量來自誰
SCDATA_USER_AGENT = config.get(
    'SCDATA', 'USER_AGENT',
    fallback='sc-tool-web/1.0 (unofficial SC fan tool; set USER_AGENT in config.ini)')

# UEX API token 屬機密，只從環境變數讀，不放 config.ini
UEX_API_TOKEN = environ.get('UEX_API_TOKEN', '').strip()

# Discord bot 參數（token 屬機密，只從環境變數讀）
DISCORD_TOKEN = environ.get('DISCORD_TOKEN', '').strip()
DISCORD_GUILD_ID = environ.get('DISCORD_GUILD_ID', '').strip()
# 動公會共享庫需要的 Discord 角色名稱或角色 ID；留空 = 所有人都能動
WMS_OPERATOR_ROLE = environ.get('WMS_OPERATOR_ROLE', '').strip()
# 庫存範圍。Web 與 Discord bot 共用同一個值才會看到同一份庫存；
# 要讓不同公會各自獨立時才改成不同值。
WMS_SCOPE_ID = environ.get('WMS_SCOPE_ID', 'default').strip() or 'default'
