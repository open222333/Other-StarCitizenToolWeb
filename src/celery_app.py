from celery import Celery
from src import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD


def _broker_url() -> str:
    auth = f':{REDIS_PASSWORD}@' if REDIS_PASSWORD else ''
    return f'redis://{auth}{REDIS_HOST}:{REDIS_PORT}/1'


def make_celery() -> Celery:
    url = _broker_url()
    app = Celery('tasks', broker=url, backend=url)
    app.config_from_object('tasks.celeryconfig')
    app.autodiscover_tasks(['tasks'])
    return app


celery_app = make_celery()
