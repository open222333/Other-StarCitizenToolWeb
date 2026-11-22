"""時間格式的共用小工具。"""
from datetime import datetime
from typing import Optional


def iso_utc(dt) -> Optional[str]:
    """naive UTC datetime → ISO 8601（秒、帶 Z），前端 new Date() 直接吃；不是 datetime 就回 None。"""
    return dt.isoformat(timespec='seconds') + 'Z' if isinstance(dt, datetime) else None
