"""啟動時的機密值健檢（fail-closed）。

## 為什麼需要這支

`.env.default` 與 `conf/config.ini.default` 是**公開**在版控裡的範本，
裡面的 `admin`／`root_password`／`flask_password`／`redis_password` 等值
等同「沒有密碼」—— 任何看過這個 repo 的人都知道。實務上最常見的意外就是
「照範本 cp 一份就上線，密碼一直沒改」，而這種錯誤不會有任何徵兆：
服務跑得好好的，直到有人從外面連進來。

所以這裡採 fail-closed：偵測到範本值或常見弱密碼就**拒絕啟動**，
而不是印一行警告了事（警告會被忽略，這正是它上次沒被發現的原因）。

## 為什麼獨立成一個模組

`run.py` 是 gunicorn 的進入點（`gunicorn -c gunicorn.py "run:app"`），
在 import 階段就會做這些檢查、必要時 `SystemExit`。那種 top-level 程式碼
沒辦法寫測試，所以判斷邏輯放這裡（純函式、無副作用），
`run.py` 只負責把值餵進來並決定怎麼中止。

## 機密值的單一來源

密碼一律以**環境變數（`.env`）為準**，`conf/config.ini` 不再存機密值 ——
config.ini 是納入版控的（生產機靠 git pull 拿到它），把密碼寫在那裡等於
輪替之後就把真密碼提交進 git。`src/__init__.py` 因此改成「環境變數優先，
config.ini 只當舊設定的相容 fallback」。
"""

# 一律拒絕的值：範本值 + 常見弱密碼。
#
# 比對時會 strip() 並轉小寫，所以 'Admin' / ' admin ' 同樣會被擋。
# 這裡刻意只列「等同沒有密碼」的值，不做長度或複雜度規則 ——
# 目的是擋住「忘記改範本」這個具體錯誤，不是當密碼強度審查員。
WEAK_SECRETS = {
    '',
    # .env.default / config.ini.default 的範本值
    'admin',
    'root_password',
    'flask_password',
    'redis_password',
    'mongo_password',
    'your_password_here',
    # 常見弱密碼
    'password',
    'passwd',
    'changeme',
    'change_me',
    '123456',
    '12345678',
    'secret',
    'test',
    'root',
}

_GENERATE_HINT = (
    "        產生一組強密碼：\n"
    "        python3 -c \"import secrets,string;a=string.ascii_letters+string.digits;"
    "print(''.join(secrets.choice(a) for _ in range(24)))\""
)


def is_weak_secret(value) -> bool:
    """這個值是否等同「沒有密碼」（範本值或常見弱密碼）。"""
    return str(value or '').strip().lower() in WEAK_SECRETS


def collect_weak_secrets(items) -> list:
    """檢查一組機密值，回傳「有問題的說明字串」清單（沒問題就是空 list）。

    `items` 是 `(名稱, 值, required)` 的序列：

    - `required=True`：一定要設，且不能是弱值（例：`REDIS_PASSWORD`，
      Rate Limiting 與 Celery broker 都靠它）
    - `required=False`：可以留空（代表沒在用這個服務），
      但**一旦填了就不能是弱值**（例：`MYSQL_PASSWORD` —— 本專案預設
      不啟用 mysql，留空是正常狀態）
    """
    problems = []
    for name, value, required in items:
        raw = str(value or '').strip()
        if not raw:
            if required:
                problems.append(f'{name} 未設定')
            continue
        if is_weak_secret(raw):
            problems.append(f'{name} 使用了範本值或弱密碼')
    return problems


def format_startup_error(problems) -> str:
    """把 `collect_weak_secrets()` 的結果組成可以直接丟給 SystemExit 的訊息。"""
    lines = ['[init] 拒絕啟動：以下機密值不安全或未設定 ——']
    lines += [f'        • {p}' for p in problems]
    lines.append('')
    lines.append('        請在 .env 設定強密碼後再啟動（密碼一律以 .env 為準，')
    lines.append('        不要寫回 conf/config.ini —— 那個檔案有納入版控）。')
    lines.append(_GENERATE_HINT)
    return '\n'.join(lines)
