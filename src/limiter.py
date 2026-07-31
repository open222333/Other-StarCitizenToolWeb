from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from src import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB


def _storage_uri() -> str:
    auth = f':{REDIS_PASSWORD}@' if REDIS_PASSWORD else ''
    return f'redis://{auth}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_storage_uri(),
)
