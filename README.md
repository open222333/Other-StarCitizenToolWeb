# Python-FlaskAPI

Flask API 框架範本，整合以下功能，可直接作為新專案的起始模板：

- **Swagger UI**（flasgger）— 自動產生 API 文件
- **JWT 認證** + **角色權限**（admin / operator / viewer）
- **後台管理 UI**（Vue 3 + Bootstrap 5，支援行動裝置）
- **資料庫整合**：MongoDB、MySQL、Redis
- **Celery**：背景任務（worker）+ 排程（beat）
- **Docker 部署**：nginx + Flask + MongoDB + MySQL + Redis，一鍵啟動
- **安全強化**：Rate Limiting（Flask-Limiter + Redis）、Security Headers、MAX_CONTENT_LENGTH

測試環境：Python 3.13 / Node 22

---

## 目錄

- [專案結構](#專案結構)
- [快速開始（本機）](#快速開始本機)
- [Docker 部署](#docker-部署)
- [域名部署（HTTPS）](#域名部署https)
- [主機 nginx 部署](#主機-nginx-部署)
- [API 說明](#api-說明)
- [設定檔說明](#設定檔說明)
- [擴充模組教學](#擴充模組教學)
- [注意事項](#注意事項)

---

## 專案結構

```
Python-FlaskAPI/
├── run.py                              # 啟動入口（自動產生 SECRET_KEY、建立預設 admin）
├── celery_worker.py                    # Celery worker / beat 入口
├── gunicorn.py                         # Gunicorn 設定（讀取 conf/config.ini [GUNICORN]）
├── requirements.txt
│
├── docker-compose.yml.default          # 入口主檔（include 以下四個服務檔）
├── docker-compose.db.yml               # MongoDB + MySQL + Redis
├── docker-compose.api.yml              # Flask API
├── docker-compose.worker.yml           # Celery worker + beat
├── docker-compose.nginx.yml            # nginx
├── docker-compose.no-nginx.yml.sample  # 主機 nginx 模式範本
├── .env.default                        # 環境變數範本
│
├── frontend/                           # Vue 3 後台管理 UI
│   ├── src/
│   ├── package.json
│   └── vite.config.js                  # outDir → ../app/static/admin，base → /admin/
│
├── app/                                # Flask 應用程式
│   ├── __init__.py                     # 初始化、Swagger / JWT 設定、藍圖註冊
│   ├── auth/view.py                    # POST /auth/login → 回傳 JWT token
│   ├── user/view.py                    # 使用者 CRUD（admin 限定）
│   ├── admin/view.py                   # GET /admin/ → 後台 UI
│   ├── log/view.py                     # GET /log/ → 操作紀錄
│   ├── sample/
│   │   ├── view.py                     # 範例路由
│   │   └── doc/sample.yaml             # Swagger 文件
│   ├── static/admin/                   # Vue build 輸出（npm run build 產生，不納入版控）
│   └── templates/admin/index.html      # Vue SPA 入口頁（Flask 回傳給瀏覽器）
│
├── tasks/                              # Celery 任務定義
├── conf/
│   ├── config.py                       # Flask Config 類別
│   ├── config.ini.default              # 設定範本 ← 複製為 config.ini
│   ├── flask.json.default              # SECRET_KEY 範本（首次啟動自動產生）
│   └── nginx/
│       ├── nginx.conf                  # nginx 主設定（worker / gzip / log 格式）
│       ├── certs/cloudflare/           # Cloudflare 憑證放置目錄
│       ├── conf.d/                     # nginx envsubst 模板（依 NGINX_MODE 選用）
│       │   ├── default.conf.http.template
│       │   ├── default.conf.cloudflare.template
│       │   └── default.conf.https-letsencrypt.template
│       └── host/                       # 主機 nginx 設定範本（主機 nginx 模式使用）
│           ├── http.conf
│           ├── cloudflare.conf
│           └── https-letsencrypt.conf
│
├── src/
│   ├── __init__.py                     # 讀取全部設定參數
│   ├── mongo.py                        # MongoDB singleton
│   ├── mysql.py                        # MySQL 連線 pool（query / execute）
│   ├── redis_client.py                 # Redis singleton
│   ├── permissions.py                  # @require_role 裝飾器
│   └── models/
│       ├── user.py                     # User model（bcrypt 加密）
│       └── log.py                      # Log model
└── logs/
```

---

## 快速開始（本機）

### 1. 複製設定檔

```bash
cp conf/config.ini.default conf/config.ini
```

> `conf/flask.json` 由 `run.py` 首次啟動時自動建立並寫入 `SECRET_KEY`，無需手動複製。

### 2. 設定資料庫連線

編輯 `conf/config.ini`（不需要的資料庫保持預設值即可）：

```ini
[MONGO]
MONGO_URI=mongodb://localhost:27017
MONGO_DB=flask_app

[MYSQL]
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=flask_app

[REDIS]
REDIS_HOST=localhost
REDIS_PASSWORD=
```

### 3. 安裝套件並啟動

```bash
pip install -r requirements.txt
python run.py
```

首次啟動會自動建立預設帳號 `admin / admin`，**請立即登入後台修改密碼**。

| 服務 | 網址 |
|---|---|
| 後台管理 | http://127.0.0.1:5000/admin/ |
| Swagger UI | http://127.0.0.1:5000/apidocs |

### 4. 前端開發（Vue）

後台 UI 以 Vue 3 開發，本機開發時啟動 Vite dev server，API 請求自動代理到 Flask：

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173/admin/
```

> Flask（port 5000）必須同時執行，Vite 才能正確代理 API 請求。

前端修改完成後，執行 build 將靜態檔輸出到 Flask 靜態目錄：

```bash
npm run build   # 輸出至 ../app/static/admin/
```

> Docker 部署時 build 步驟由 Dockerfile multi-stage 自動處理，**不需手動執行**。

---

## Docker 部署

架構：`nginx（對外）→ api（Flask）→ MongoDB / MySQL / Redis`

```
使用者 → nginx:80 → api:5000 → MongoDB / MySQL / Redis
                 ↘ worker / beat（背景任務）
```

### 1. 準備設定檔

```bash
cp docker-compose.yml.default docker-compose.yml
cp .env.default .env
cp conf/config.ini.default conf/config.ini
```

> `conf/flask.json` 由容器首次啟動時自動建立，無需手動複製。

### 2. 調整 config.ini（主機名稱改為 Docker 服務名稱）

```ini
[MONGO]
MONGO_URI=mongodb://mongo:27017
MONGO_DB=flask_app

[MYSQL]
MYSQL_HOST=mysql
MYSQL_USER=flask_user
MYSQL_PASSWORD=flask_password
MYSQL_DB=flask_app

[REDIS]
REDIS_HOST=redis
REDIS_PASSWORD=redis_password
```

### 3. 首次啟動（建置 image）

```bash
docker compose up -d --build
```

> `--build` 會執行 multi-stage build：先在容器內 `npm run build` 打包 Vue，再建置 Flask image。之後若只修改 Python 程式碼，重啟即可，不需重新 build：
>
> ```bash
> docker compose restart api
> ```
>
> 只有異動 `frontend/`、`requirements.txt` 或 `Dockerfile` 時，才需要再加 `--build`。

### 服務一覽

| 服務 | 映像 | 說明 |
|---|---|---|
| `nginx` | nginx:1.26-alpine | 反向代理，對外唯一入口（port 80 / 443） |
| `api` | 本地建置（python:3.13-slim） | Flask API，以非 root 使用者執行 |
| `worker` | 同 `api` image | Celery worker（背景任務） |
| `beat` | 同 `api` image | Celery beat（排程任務） |
| `mongo` | mongo:7 | MongoDB（僅內部） |
| `mysql` | mysql:8.0 | MySQL（僅內部） |
| `redis` | redis:7-alpine | Redis（僅內部） |

啟動後透過 nginx 存取：

| 服務 | 網址 |
|---|---|
| 後台管理 | http://localhost/admin/ |
| Swagger UI | http://localhost/apidocs |
| 健康檢查 | http://localhost/ |

### 常用指令

```bash
docker compose ps                     # 查看各服務狀態
docker compose logs -f api            # 即時查看 Flask 日誌
docker compose logs -f nginx          # 即時查看 nginx 日誌
docker compose logs -f worker         # 即時查看 Celery worker 日誌
docker compose exec api bash          # 進入 Flask 容器
docker compose restart api            # 重啟 Flask（Python 程式碼異動後）
docker compose restart nginx          # 重載 nginx 設定
docker compose down                   # 停止所有服務
docker compose down -v                # 停止並清除資料（不可逆）
docker compose build --no-cache api   # 重新建置 Flask + Vue
```

---

## 域名部署（HTTPS）

nginx 模式透過 `.env` 的 `NGINX_MODE` 控制，不需手動換設定檔，改完 `.env` 重啟即可。

| `NGINX_MODE` | 說明 | 適用情境 |
|---|---|---|
| `http` | 純 HTTP（預設） | 本機、無域名、內網 |
| `cloudflare` | Cloudflare Origin CA SSL | 域名走 Cloudflare 代理 |
| `https-letsencrypt` | Let's Encrypt SSL | 自行管理憑證 |

---

### 模式一：HTTP（預設）

`.env` 保持預設即可：

```env
NGINX_MODE=http
DOMAIN=_
```

---

### 模式二：Cloudflare SSL

#### 1. DNS 設定

Cloudflare Dashboard → 你的域名 → DNS → 新增 A Record：

```
類型   名稱   值              Proxy
A      @      伺服器 IP       ☁ Proxied
```

#### 2. 伺服器開放 Port

```bash
ufw allow 80 && ufw allow 443
```

#### 3. 建立 Cloudflare Origin CA 憑證

Cloudflare Dashboard → **SSL/TLS → Origin Server → Create Certificate**

- 選 RSA，有效期 15 年
- 複製 **Origin Certificate** 和 **Private Key**

```bash
mkdir -p /etc/ssl/cloudflare
nano /etc/ssl/cloudflare/origin.pem   # 貼上 Origin Certificate
nano /etc/ssl/cloudflare/origin.key   # 貼上 Private Key
chmod 600 /etc/ssl/cloudflare/origin.key
```

#### 4. 更新 `.env`

```env
NGINX_MODE=cloudflare
DOMAIN=your.domain.com
CF_CERT_DIR=/etc/ssl/cloudflare
```

#### 5. 啟動

```bash
docker compose up -d
```

> Cloudflare SSL/TLS 模式記得設為 **Full (Strict)**，確保端對端加密。

---

## 主機 nginx 部署

**適用情境**：主機上已安裝 nginx（或已有其他服務佔用 80/443 port），不希望在 Docker 中額外跑一個 nginx 容器。

```
使用者 → 主機 nginx:80/443 → 127.0.0.1:5000（Docker api 容器）→ 資料庫容器
```

### Step 1：準備 no-nginx compose 檔

```bash
cp docker-compose.no-nginx.yml.sample docker-compose.no-nginx.yml
cp .env.default .env
cp conf/config.ini.default conf/config.ini
```

> `docker-compose.no-nginx.yml` 已將 `api` 的 port 綁定為 `127.0.0.1:5000`，只讓主機 nginx 連入，不直接對外暴露。

調整 `conf/config.ini` 的主機名稱（同 Docker 部署 Step 2）。

### Step 2：安裝 nginx（Ubuntu / Debian）

```bash
sudo apt update && sudo apt install -y nginx
sudo systemctl enable --now nginx
```

### Step 3：建立 nginx 站台設定

```bash
# ── 模式一：HTTP ────────────────────────────────────────────────
sudo cp conf/nginx/host/http.conf /etc/nginx/sites-available/flask-app
sudo nano /etc/nginx/sites-available/flask-app
# 將 YOUR_DOMAIN 改為實際域名，或改為 _ 接受所有請求

# ── 模式二：Cloudflare Origin CA SSL ──────────────────────────
# 前置：建立 Cloudflare 憑證（參見模式二說明）
sudo cp conf/nginx/host/cloudflare.conf /etc/nginx/sites-available/flask-app
sudo nano /etc/nginx/sites-available/flask-app
# 將 YOUR_DOMAIN 替換為實際域名（共 2 處）

# ── 模式三：Let's Encrypt SSL ──────────────────────────────────
sudo apt install -y certbot python3-certbot-nginx
# 先用模式一啟動 nginx，再申請憑證：
sudo certbot certonly --nginx -d your.domain.com
sudo cp conf/nginx/host/https-letsencrypt.conf /etc/nginx/sites-available/flask-app
sudo nano /etc/nginx/sites-available/flask-app
# 將所有 YOUR_DOMAIN 替換為實際域名（共 4 處）
```

### Step 4：啟用站台並重載

```bash
sudo ln -sf /etc/nginx/sites-available/flask-app /etc/nginx/sites-enabled/flask-app
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Step 5：啟動 Docker 容器

```bash
docker compose -f docker-compose.no-nginx.yml up -d --build
```

### 常用指令

```bash
sudo nginx -t                                        # 驗證設定語法
sudo systemctl reload nginx                          # 重載（不中斷連線）
sudo systemctl restart nginx                         # 完整重啟
sudo tail -f /var/log/nginx/flask-app-error.log     # 錯誤日誌
sudo tail -f /var/log/nginx/flask-app-access.log    # 訪問日誌
sudo certbot renew --dry-run                         # 測試 Let's Encrypt 自動續約
```

---

## API 說明

### 公開端點

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/` | 健康檢查 |
| POST | `/auth/login` | 登入，回傳 JWT token |
| GET | `/admin/` | 後台管理 UI |
| GET | `/apidocs` | Swagger UI |
| GET | `/sample/check/<domain>` | 域名格式驗證範例 |

### 受保護端點（需 `Authorization: Bearer <token>`）

| 方法 | 路徑 | 所需角色 | 說明 |
|---|---|---|---|
| GET | `/user/` | admin | 列出使用者 |
| POST | `/user/` | admin | 新增使用者 |
| PUT | `/user/<id>` | admin | 更新密碼或角色 |
| DELETE | `/user/<id>` | admin | 刪除使用者 |
| GET | `/log/` | 已登入 | 查詢操作紀錄 |

### 登入取得 Token

**本機開發（port 5000）**

```bash
curl -X POST http://127.0.0.1:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
# {"success": true, "token": "<jwt>", "role": "admin"}

curl http://127.0.0.1:5000/user/ \
  -H "Authorization: Bearer <jwt>"
```

**Docker 部署（port 80，經 nginx）**

```bash
curl -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

curl http://localhost/user/ \
  -H "Authorization: Bearer <jwt>"
```

---

## 設定檔說明

### conf/config.ini

| 區塊 | 參數 | 說明 | 預設值 |
|---|---|---|---|
| `[LOG]` | `LOG_DISABLE` | 關閉 log（1=關閉） | `False` |
| | `LOG_PATH` | log 目錄 | `logs` |
| | `LOG_LEVEL` | 等級（DEBUG/INFO/WARNING/ERROR/CRITICAL） | `WARNING` |
| | `LOG_FILE_DISABLE` | 關閉寫入檔案（1=關閉） | `False` |
| `[SETTING]` | `FLASK_JSON_PATH` | flask.json 路徑 | `conf/flask.json` |
| | `ADMIN_TITLE` | 後台管理頁面名稱 | `後台管理` |
| `[GUNICORN]` | `WORKERS` | Worker 數（建議 2×CPU+1） | `3` |
| | `BIND` | 綁定位址 | `0.0.0.0:5000` |
| | `TIMEOUT` | 請求逾時（秒） | `120` |
| `[MONGO]` | `MONGO_URI` | MongoDB 連線 URI | `mongodb://localhost:27017` |
| | `MONGO_DB` | 資料庫名稱 | `flask_app` |
| `[MYSQL]` | `MYSQL_HOST` | 主機 | `localhost` |
| | `MYSQL_PORT` | 埠號 | `3306` |
| | `MYSQL_USER` | 使用者 | `root` |
| | `MYSQL_PASSWORD` | 密碼 | _(空)_ |
| | `MYSQL_DB` | 資料庫名稱 | `flask_app` |
| `[REDIS]` | `REDIS_HOST` | 主機 | `localhost` |
| | `REDIS_PORT` | 埠號 | `6379` |
| | `REDIS_PASSWORD` | 密碼 | _(空)_ |
| | `REDIS_DB` | DB 編號 | `0` |

### 環境變數（.env）

| 變數 | 說明 | 預設值 |
|---|---|---|
| `FLASK_PORT` | Flask 內部埠號 | `5000` |
| `NGINX_MODE` | nginx 模式（`http` / `cloudflare` / `https-letsencrypt`） | `http` |
| `DOMAIN` | 域名（HTTP 模式填 `_` 即可） | `_` |
| `CF_CERT_DIR` | Cloudflare 憑證目錄 | `./conf/nginx/certs/cloudflare` |
| `JWT_ACCESS_TOKEN_EXPIRES_HOURS` | Token 有效時數 | `8` |
| `ADMIN_PASSWORD` | 首次啟動建立的 admin 密碼 | `admin` |
| `MYSQL_ROOT_PASSWORD` | MySQL root 密碼 | `root_password` |
| `MYSQL_DATABASE` | MySQL 資料庫名稱 | `flask_app` |
| `MYSQL_USER` | MySQL 應用程式帳號 | `flask_user` |
| `MYSQL_PASSWORD` | MySQL 應用程式密碼 | `flask_password` |
| `REDIS_PASSWORD` | Redis 密碼 | `redis_password` |

### conf/flask.json

```json
{ "SECRET_KEY": "" }
```

`SECRET_KEY` 留空時，`run.py` 啟動會自動產生並寫入，此檔案不納入版控。

---

## 擴充模組教學

以新增「商品管理」模組為例，說明完整擴充流程。

### 步驟一：建立 Blueprint

```
app/product/
├── __init__.py    （空白）
└── view.py
```

```python
# app/product/view.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from src.permissions import require_role

app_product = Blueprint('app_product', __name__)

@app_product.route('/', methods=['GET'])
@jwt_required()
def list_products():
    return jsonify({'success': True, 'data': []})

@app_product.route('/', methods=['POST'])
@jwt_required()
@require_role('admin', 'operator')
def create_product():
    data = request.get_json()
    return jsonify({'success': True}), 201
```

### 步驟二：選擇資料存取方式

**MongoDB**

```python
# src/models/product.py
from datetime import datetime
from src.mongo import get_db

class Product:
    COLLECTION = 'products'

    @classmethod
    def find_all(cls) -> list:
        return list(get_db()[cls.COLLECTION].find({}, {'_id': 0}))

    @classmethod
    def create(cls, name: str, price: float) -> str:
        result = get_db()[cls.COLLECTION].insert_one({
            'name': name, 'price': price, 'created_at': datetime.utcnow()
        })
        return str(result.inserted_id)
```

**MySQL**

```python
from src.mysql import query, execute

rows = query('SELECT id, name, price FROM products ORDER BY id DESC')
execute('INSERT INTO products (name, price) VALUES (%s, %s)', (name, price))
```

**Redis 快取**

```python
import json
from src.redis_client import get_redis

CACHE_KEY = 'products:all'
CACHE_TTL = 60

def list_products():
    r = get_redis()
    cached = r.get(CACHE_KEY)
    if cached:
        return jsonify({'success': True, 'data': json.loads(cached)})
    rows = query('SELECT * FROM products')
    r.setex(CACHE_KEY, CACHE_TTL, json.dumps(rows))
    return jsonify({'success': True, 'data': rows})

def create_product():
    execute('INSERT INTO products (name, price) VALUES (%s, %s)', (name, price))
    get_redis().delete(CACHE_KEY)
```

### 步驟三：註冊藍圖

```python
# app/__init__.py
from app.product.view import app_product

def create_app(config_object=None):
    ...
    app.register_blueprint(blueprint=app_product, url_prefix='/product')
```

### 步驟四：（選用）Swagger 文件

```yaml
# app/product/doc/list_products.yaml
summary: 商品列表
tags:
  - Product
security:
  - Bearer: []
responses:
  200:
    description: 成功
```

```python
from flasgger import swag_from
import os

@app_product.route('/', methods=['GET'])
@jwt_required()
@swag_from(os.path.join('doc', 'list_products.yaml'))
def list_products():
    ...
```

### 步驟五：（選用）擴充後台 UI

編輯 [frontend/src/](frontend/src/) 對應頁面，`npm run build` 後重啟 `api` 容器即可。

---

### 角色說明

| 角色 | 可存取範圍 |
|---|---|
| `admin` | 完整權限（含使用者管理） |
| `operator` | 一般操作（不可管理使用者） |
| `viewer` | 唯讀 |

```python
@require_role('admin')              # 僅 admin
@require_role('admin', 'operator')  # admin 或 operator
```

### 寫入操作紀錄

```python
from src.models.log import Log
from flask_jwt_extended import get_jwt_identity

Log.create(
    username=get_jwt_identity(),
    action='create_product',
    detail=f'name={name}',
    success=True
)
```

---

## 注意事項

| 項目 | 說明 |
|---|---|
| `conf/flask.json` | 首次啟動自動產生，已加入 `.gitignore`，**勿提交版控** |
| `docker-compose.yml` | 由 `docker-compose.yml.default` 複製而來，已加入 `.gitignore` |
| `docker-compose.no-nginx.yml` | 由 `docker-compose.no-nginx.yml.sample` 複製而來，已加入 `.gitignore` |
| `app/static/admin/` | Vue build 輸出，已加入 `.gitignore`（Docker build 時自動產生） |
| 環境變數密碼 | `.env` 中的密碼均為範本預設值，**正式環境務必修改** |
| 預設帳號 | `admin / admin`，**首次啟動後立即修改**；可透過 `ADMIN_PASSWORD` 環境變數預設密碼 |
| Rate Limiting | `/auth/login` 限制 10 次/分鐘，`/auth/refresh` 限制 30 次/分鐘（Redis 跨 Worker 共享計數） |
| Security Headers | 所有回應自動加入 `X-Frame-Options`、`X-Content-Type-Options` 等安全標頭 |
| MAX_CONTENT_LENGTH | 請求 body 上限 16 MB，超過回傳 `413` |
| MongoDB Index | 啟動時自動建立 `users.username`（unique）與 `logs.created_at` 索引 |
| debug 模式 | 預設開啟（`TestingConfig`），正式部署請改用 `ProductionConfig` |
| MySQL / Redis | 選用功能，不設定 `config.ini` 對應區塊即不啟用 |
