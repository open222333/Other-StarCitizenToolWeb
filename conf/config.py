import json
from datetime import timedelta
from os import environ
from src import FLASK_JSON_PATH, JWT_ACCESS_TOKEN_EXPIRES_HOURS, JWT_REFRESH_TOKEN_EXPIRES_DAYS

with open(FLASK_JSON_PATH, 'r') as f:
    conf = json.loads(f.read())


class BasicConfig(object):
    """基本設定"""
    SECRET_KEY                  = conf['SECRET_KEY']
    JWT_SECRET_KEY              = conf['SECRET_KEY']
    JWT_ACCESS_TOKEN_EXPIRES    = timedelta(hours=JWT_ACCESS_TOKEN_EXPIRES_HOURS)
    JWT_REFRESH_TOKEN_EXPIRES   = timedelta(days=JWT_REFRESH_TOKEN_EXPIRES_DAYS)
    JSON_AS_ASCII               = False
    JSON_SORT_KEYS              = True
    MAX_CONTENT_LENGTH          = 16 * 1024 * 1024  # 16 MB


class ProductionConfig(BasicConfig):
    DB_SERVER = environ.get('DB_SERVER', '127.0.0.1')


class DevelopmentConfig(BasicConfig):
    DB_SERVER = 'localhost'


class TestingConfig(BasicConfig):
    TESTING      = False
    DEBUG        = False
    DB_SERVER    = 'localhost'
    DATABASE_URI = 'sqlite:///:memory:'
