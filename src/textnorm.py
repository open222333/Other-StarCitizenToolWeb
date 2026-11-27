"""船名、品項名比對用的正規化（RSI 商店／升級工具／借用船清單／載具主檔之間對名字）。

Unofficial Star Citizen fan tool. Not affiliated with the Cloud Imperium group of companies.
"""
import re

_NON_ASCII_WORD = re.compile(r'[^0-9a-z]+')


def norm_ascii(text) -> str:
    """小寫、只留英數字與單一空白：「Hercules Starlifter M2」「M2  Hercules」「F7C-R Mk II」這種空白／標點差異不影響。
    中文會被當成分隔字元拿掉；要保留中文的搜尋用 src/models/name_search.py 那份。"""
    return ' '.join(_NON_ASCII_WORD.sub(' ', str(text or '').lower()).split())
