"""ProxyFix 迴歸測試。

背景：api 容器在 docker-compose.api.yml 只用 `expose:`，不會發布到 host，
外部連線一定先經過 nginx 或 web 容器 —— 兩邊的 nginx conf 都正確設定了
X-Forwarded-For／X-Real-IP。但如果 Flask 這邊沒有掛 ProxyFix 去信任這層
代理，Flask-Limiter 用來分辨「同一個人」的 get_remote_address() 讀到的
會是 request.remote_addr，也就是 nginx 容器在 docker network 裡的內部
IP —— 對 Flask 而言每個訪客長得都一樣，所有 rate limit（/player/login、
/player/register、/player/me/password 的「10 per minute」等）會變成整個
公會共用同一份額度：一個人多按幾次，或剛好幾個成員同時登入，就會讓其他人
平白被 429 擋下來，也讓 rate limit 完全失去「擋單一來源暴力破解」的意義。

直接用原始 WSGI 呼叫 app.wsgi_app，略過 Flask routing —— ProxyFix 是在
routing 之前的 WSGI middleware 層工作，呼叫路徑對不對不重要，只要看
environ 有沒有在傳進 Flask 之前就被改寫。這樣寫也不會受 pytest 執行順序
影響（不像動態註冊路由/hook，在 Flask 2.2 對「app 已經處理過請求」的舊限制
下可能出問題）。
"""
from io import BytesIO


def _build_environ(remote_addr, forwarded_for=None):
    environ = {
        'REQUEST_METHOD':     'GET',
        'PATH_INFO':          '/',
        'SERVER_NAME':        'test',
        'SERVER_PORT':        '80',
        'SERVER_PROTOCOL':    'HTTP/1.1',
        'wsgi.version':       (1, 0),
        'wsgi.url_scheme':    'http',
        'wsgi.input':         BytesIO(b''),
        'wsgi.errors':        BytesIO(),
        'wsgi.multithread':   False,
        'wsgi.multiprocess':  False,
        'wsgi.run_once':      False,
        'REMOTE_ADDR':        remote_addr,
    }
    if forwarded_for:
        environ['HTTP_X_FORWARDED_FOR'] = forwarded_for
    return environ


def _call(flask_app, environ):
    captured = {}

    def start_response(status, headers):
        captured['status'] = status

    body = flask_app.wsgi_app(environ, start_response)
    # 把 WSGI iterable 耗盡（有些實作要跑完才會真的觸發整個請求生命週期）
    list(body)
    return captured


def test_remote_addr_trusts_nginx_forwarded_for():
    """有 X-Forwarded-For 時，REMOTE_ADDR 要換成訪客的真實 IP。"""
    from app import app as flask_app

    # 172.18.0.5：模擬 nginx 容器在 docker network 裡看到的「上一手」IP
    env = _build_environ(remote_addr='172.18.0.5', forwarded_for='203.0.113.5')
    _call(flask_app, env)

    assert env['REMOTE_ADDR'] == '203.0.113.5', (
        'ProxyFix 沒有把 REMOTE_ADDR 換成 X-Forwarded-For 帶來的真實 IP —— '
        'Flask-Limiter 的 get_remote_address() 會繼續拿到 nginx 自己的 IP，'
        '等於整個公會共用同一份 rate limit 額度（見檔頭說明）'
    )


def test_remote_addr_falls_back_without_forwarded_header():
    """沒有 X-Forwarded-For（例如測試環境、或有人直連 api 容器）時，
    維持原本的 REMOTE_ADDR，不應該爆炸或誤信一個不存在的標頭。"""
    from app import app as flask_app

    env = _build_environ(remote_addr='172.18.0.5')
    _call(flask_app, env)

    assert env['REMOTE_ADDR'] == '172.18.0.5'


def test_proxy_fix_trusts_exactly_one_hop():
    """只信任最右邊那一個 hop —— 多一層偽造的 X-Forwarded-For 不該被當真。

    ProxyFix(x_for=1) 只採用 X-Forwarded-For 最後一個值（緊鄰 nginx 那個），
    前面偽造的值會被當成「client 自己亂帶的標頭」忽略掉，不會被誤信為
    真實來源 IP。這是 x_for=1（只有一層代理）這個參數本身該有的行為 ——
    如果之後有人為了多層代理把它改大，這支測試會先被改壞，提醒要重新
    確認代理層數。
    """
    from app import app as flask_app

    # 訪客宣稱自己是 203.0.113.5，但真正連到 nginx 的是 203.0.113.5, 198.51.100.9
    # （最後一個 198.51.100.9 才是 nginx 直接看到的「上一手」）
    env = _build_environ(remote_addr='172.18.0.5',
                          forwarded_for='203.0.113.5, 198.51.100.9')
    _call(flask_app, env)

    assert env['REMOTE_ADDR'] == '198.51.100.9'
