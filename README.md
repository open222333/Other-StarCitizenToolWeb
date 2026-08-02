# StarCitizenToolWeb

星際公民（Star Citizen）倉庫管理系統。Flask API + Vue 3 後台 + Discord bot，
遊戲資料從社群 API 同步到本地 MongoDB 當作 Item Master。

```
Star Citizen Wiki API ─┐
                       ├─→ Celery beat (每日) ─→ MongoDB ─┬─→ Flask API + Vue 後台
UEX Corp API 2.0      ─┘                                  └─→ Discord bot（斜線指令）
```

基礎功能（承襲 Flask API 範本）：Swagger UI、JWT 認證 + 角色權限（admin / operator / viewer）、
Vue 3 後台、MongoDB / MySQL / Redis、Celery worker + beat、Rate Limiting、Security Headers。

測試環境：Python 3.13 / Node 22

> **非官方專案。** CIG 沒有提供官方 API，所有遊戲資料來自社群眾包／解包的第三方來源。
> 詳見文末的[免責聲明](#免責聲明)。

---

## 目錄

- [專案結構](#專案結構)
- [環境事實](#環境事實)
- [快速開始（本機）](#快速開始本機)
- [Docker 部署](#docker-部署)
- [域名部署（HTTPS）](#域名部署https)
- [主機 nginx 部署](#主機-nginx-部署)
- [遊戲資料同步](#遊戲資料同步)
- [Discord bot](#discord-bot)
- [API 說明](#api-說明)
- [備份與還原](#備份與還原)
- [危險操作清單](#危險操作清單)
- [設定檔說明](#設定檔說明)
- [擴充模組教學](#擴充模組教學)
- [注意事項](#注意事項)
- [AI 協作制度](#ai-協作制度)

---

## 專案結構

```
StarCitizenToolWeb/
├── run.py                              # 啟動入口（自動產生 SECRET_KEY、建立預設 admin）
├── celery_worker.py                    # Celery worker / beat 入口
├── gunicorn.py                         # Gunicorn 設定
│
├── docker-compose.yml.default          # 入口主檔（include 以下五個服務檔）
├── docker-compose.db.yml               # MongoDB + MySQL + Redis
├── docker-compose.api.yml              # Flask API
├── docker-compose.worker.yml           # Celery worker + beat
├── docker-compose.bot.yml              # Discord bot          ← 星際公民功能
├── docker-compose.nginx.yml            # nginx
│
├── frontend/                           # Vue 3 後台管理 UI
│
├── app/                                # Flask 藍圖
│   ├── auth/ user/ admin/ log/ device/ docs/ sample/
│   ├── item/view.py                    # /item/       遊戲主檔查詢（唯讀）
│   └── inventory/view.py               # /inventory/  庫存查詢與異動
│
├── bot/                                # Discord bot（斜線指令）
│   ├── main.py                         # 進入點：python -m bot.main
│   ├── db.py                           # 把 src/models 的同步呼叫包成 async
│   ├── ui.py                           # embed 樣式、分頁按鈕、權限判斷
│   ├── completers.py                   # autocomplete（value 一律是遊戲 uuid）
│   └── cogs/                           # binding / inventory / stock / prices
│
├── src/
│   ├── __init__.py                     # 讀取全部設定參數
│   ├── mongo.py                        # MongoDB singleton + ensure_indexes()
│   ├── scdata.py                        # 社群 API 抓取與欄位映射
│   ├── permissions.py                  # @require_role 裝飾器
│   └── models/
│       ├── user.py log.py device_token.py user_template.py
│       ├── item.py                     # 主檔唯讀模型（Item / Vehicle / Commodity）
│       └── inventory.py                # 庫存邏輯（Web 與 bot 共用的單一事實來源）
│
├── tasks/
│   ├── celeryconfig.py                 # Beat 排程
│   ├── scheduled.py                    # 清日誌、健康檢查
│   └── scdata_sync.py                  # 遊戲主檔同步
│
├── conf/                               # config.ini、nginx 設定
└── tests/                              # pytest（mongomock，不需外部服務）
```

### 資料流與所有權

```
tasks/scdata_sync.py ──寫入──→ item_master / vehicle_master / commodity_master
                                        ↑ 唯讀
                     src/models/item.py ┘

src/models/inventory.py ──讀寫──→ inventory / inventory_log / discord_bindings
        ↑                    ↑
app/inventory/view.py     bot/cogs/
```

**單向所有權**：`scdata_sync` 是三個 `*_master` 的唯一寫入者，應用層只讀；
反過來同步任務完全不碰 `inventory`。要加主檔欄位就改 `src/scdata.py` 的 mapper
再重跑一次同步，不要在應用層補資料。

**庫存邏輯只有一份**：`src/models/inventory.py`。Web API 直接呼叫，Discord bot
透過 `bot/db.py` 用 `asyncio.to_thread` 呼叫同一份程式碼。不要各自實作。

---

## 環境事實

> 這一節是**當下為真的環境現狀**。環境有變動（換版本、開 port、加金鑰）時要當場更新。
> 依規定不記錄任何密碼、token、私鑰內容。

### 服務版本

| 服務 | 版本 | 來源 | 關鍵設定事實 |
|---|---|---|---|
| Flask API | python:3.13-slim | 本地建置 | Gunicorn，非 root（uid 1001）執行 |
| Celery worker / beat | 同 api image | — | worker `--concurrency=2`；beat schedule 存 `/tmp/celerybeat-schedule` |
| Discord bot | 同 api image | — | 斜線指令；不需 Message Content Intent |
| nginx | nginx:1.26-alpine | Docker Hub | 對外唯一入口；模式由 `NGINX_MODE` 決定 |
| MongoDB | mongo:7 | Docker Hub | **獨立節點，非 replica set → 不支援多文件交易** |
| MySQL | mysql:8.0 | Docker Hub | `caching_sha2_password` |
| Redis | redis:7-alpine | Docker Hub | `requirepass`；DB 0 = Rate Limit，DB 1 = Celery broker |

MongoDB 是獨立節點這件事會直接影響移庫的一致性保證，見[併發與一致性](#併發與一致性)。

### Port 對照表

| Port | 服務 | 開放範圍 |
|---|---|---|
| 80 / 443 | nginx | **對外** |
| 5000 | api | 僅 compose 內網（`expose`，未映射到主機）。主機 nginx 模式下綁 `127.0.0.1:5000` |
| 27017 | mongo | 僅 compose 內網，**不映射到主機** |
| 3306 | mysql | 僅 compose 內網，**不映射到主機** |
| 6379 | redis | 僅 compose 內網，**不映射到主機** |

三個資料庫都沒有對主機映射 port。要連進去一律走 `docker compose exec`。

### `.env` 欄位清單

只列欄位名與用途，值請見 `.env.default`。標 🔑 的是機密，正式環境必須改掉範本預設值。

| 欄位 | 用途 |
|---|---|
| `FLASK_PORT` | Flask 內部埠號 |
| `JWT_ACCESS_TOKEN_EXPIRES_HOURS` | Access token 有效時數 |
| `CORS_ORIGIN` | 額外允許的來源（逗號分隔）；`localhost:5173` 已內建 |
| 🔑 `ADMIN_PASSWORD` | 首次啟動建立 admin 帳號的密碼 |
| 🔑 `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` | MySQL root / 應用程式帳號密碼 |
| `MYSQL_DATABASE` / `MYSQL_USER` | MySQL 資料庫與帳號名稱 |
| 🔑 `REDIS_PASSWORD` | Redis 密碼 |
| `NGINX_MODE` | `http` / `cloudflare` / `https-letsencrypt` |
| `DOMAIN` | 對外域名（http 模式填 `_`） |
| `CF_CERT_DIR` | Cloudflare Origin CA 憑證目錄 |
| 🔑 `UEX_API_TOKEN` | UEX Corp API token；留空則跳過 UEX 同步 |
| `WMS_SCOPE_ID` | 庫存範圍。**Web 與 bot 必須相同才會看到同一份庫存** |
| `WMS_OPERATOR_ROLE` | 動公會共享庫需要的 Discord 角色；留空 = 所有人都能動 |
| 🔑 `DISCORD_TOKEN` | Discord bot token；留空則 bot 容器直接結束 |
| `DISCORD_GUILD_ID` | Discord 伺服器 ID；留空則註冊全域指令 |

`conf/config.ini` 的欄位見[設定檔說明](#設定檔說明)。

### 金鑰與憑證盤點

| 項目 | 用途 | 所在位置 | 備註 |
|---|---|---|---|
| `SECRET_KEY` | Flask session + JWT 簽章 | `conf/flask.json` | 首次啟動自動產生；已 gitignore。**換掉會使所有既有 token 失效** |
| Cloudflare Origin CA | nginx TLS | `CF_CERT_DIR` 指向的目錄 | RSA，有效期 15 年 |
| Let's Encrypt 憑證 | nginx TLS | `/etc/letsencrypt/live/<domain>/` | 90 天，certbot 自動續約 |
| UEX API token | 遊戲價格資料 | `.env` | 免費，可在 UEX 後台重新產生 |
| Discord bot token | Discord 登入 | `.env` | 洩漏時到 Developer Portal 按 Reset Token |

### 外部服務依賴

| 服務 | 用途 | 風險 | 備註 |
|---|---|---|---|
| [Star Citizen Wiki API](https://api.star-citizen.wiki) | 物品 / 載具 / 商品規格 | 社群自費維運，無 SLA、無公開配額 | 全量同步約 130 次請求 |
| [UEX Corp API 2.0](https://uexcorp.space/api/documentation) | 價格、終端位置 | 眾包資料可能與伺服器有落差 | 配額 120 req/min |
| Discord API | bot 指令 | 全域指令傳播最久約 1 小時 | — |

---

## 快速開始（本機）

### 1. 複製設定檔

```bash
cp conf/config.ini.default conf/config.ini
cp .env.default .env
```

> `conf/flask.json` 由 `run.py` 首次啟動自動建立並寫入 `SECRET_KEY`，無需手動複製。

### 2. 設定資料庫連線

編輯 `conf/config.ini`（不需要的資料庫保持預設值即可）：

```ini
[MONGO]
MONGO_URI=mongodb://localhost:27017
MONGO_DB=flask_app

[REDIS]
REDIS_HOST=localhost
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

### 4. 灌入遊戲資料

主檔是空的，前端與 bot 的搜尋都會沒有結果。先跑一次同步（約 5～10 分鐘）：

```bash
python -c "from tasks.scdata_sync import sync_scdata; print(sync_scdata(with_uex=False))"
```

### 5. 前端開發（Vue）

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173/admin/
```

> Flask（port 5000）必須同時執行，Vite 才能正確代理 API 請求。

```bash
npm run build   # 輸出至 ../app/static/admin/
```

> Docker 部署時 build 由 Dockerfile multi-stage 自動處理，**不需手動執行**。

### 6. 執行測試

```bash
pip install -r requirements-test.txt
pytest                              # 161 個測試，全部使用 mongomock，不需外部服務
pytest tests/test_inventory.py -v   # 只跑庫存邏輯
pytest -k capacity                  # 只跑容量計算相關
```

---

## Docker 部署

架構：`nginx（對外）→ api（Flask）→ MongoDB / MySQL / Redis`

```
使用者 → nginx:80 → api:5000 → MongoDB / MySQL / Redis
                 ↘ worker / beat（背景任務 + 遊戲資料同步）
                 ↘ bot（Discord 斜線指令）
```

### 1. 準備設定檔

```bash
cp docker-compose.yml.default docker-compose.yml
cp .env.default .env
cp conf/config.ini.default conf/config.ini
```

編輯 `.env`：**至少要改掉 `MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`、`REDIS_PASSWORD`、
`ADMIN_PASSWORD`**（範本值是公開的），並填入 `DISCORD_TOKEN`（不用 bot 就留空）。

### 2. 調整 config.ini（主機名稱改為 Docker 服務名稱）

```ini
[MONGO]
MONGO_URI=mongodb://mongo:27017
MONGO_DB=flask_app

[MYSQL]
MYSQL_HOST=mysql
MYSQL_USER=flask_user
MYSQL_PASSWORD=<與 .env 的 MYSQL_PASSWORD 一致>
MYSQL_DB=flask_app

[REDIS]
REDIS_HOST=redis
REDIS_PASSWORD=<與 .env 的 REDIS_PASSWORD 一致>
```

### 3. 首次部署

```bash
docker compose up -d --build
```

> `--build` 會執行 multi-stage build：先在容器內 `npm run build` 打包 Vue，再建置 Flask image。
> 之後只改 Python 程式碼時重啟即可；只有異動 `frontend/`、`requirements.txt`、`Dockerfile`
> 才需要再加 `--build`。

### 4. 驗證清單（部署後立即執行，全過才算完成）

```bash
# ① 所有服務健康
docker compose ps
#    api / mongo / mysql / redis / nginx 應為 Up (healthy)
#    worker / beat / bot 為 Up（這三個沒有 healthcheck）

# ② 健康端點
curl -f http://localhost/ && echo                    # 預期 ok

# ③ 登入取得 token
curl -sf -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<你的 ADMIN_PASSWORD>"}'
#    預期 {"success": true, "token": "...", "role": "admin"}

# ④ 後台 UI 有內容（不是 404、不是空白）
curl -sf http://localhost/admin/ | head -c 200

# ⑤ bot 已連上 Discord（若有設 DISCORD_TOKEN）
docker compose logs bot --tail 20 | grep -E "已登入為|已同步"

# ⑥ 遊戲資料同步狀態
docker compose exec -T mongo mongosh flask_app --quiet --eval \
  'db.item_master.countDocuments({is_current:true})'
#    首次部署會是 0，跑過同步後應為約 12,000
```

任一項不過 → 依下方回滾步驟處理，**不要在正式環境現場 debug**。

### 5. 回滾

正式環境部署前先做快照，否則回滾無所依據。

```bash
# ── 事前快照（執行 up -d 之前）─────────────────────────────
mkdir -p .deploy
git rev-parse HEAD > .deploy/rev.txt                    # 記錄目前版本
cp .env .deploy/env.$(date +%Y%m%d%H%M).bak             # 備份設定
cp conf/config.ini .deploy/config.ini.$(date +%Y%m%d%H%M).bak
docker compose exec -T mongo mongodump --archive \
  --db=flask_app --gzip > .deploy/mongo.pre.gz          # 資料備份
docker image inspect python-flask-api:latest \
  --format '{{.Id}}' > .deploy/image.txt                # 記錄目前 image

# ── 回滾（驗證未全過就執行）───────────────────────────────
git checkout $(cat .deploy/rev.txt)
cp .deploy/env.<timestamp>.bak .env
cp .deploy/config.ini.<timestamp>.bak conf/config.ini
docker compose up -d --build
# 重跑上面的驗證清單 ①～④

# ── 只有資料寫壞才需要還原資料（會覆蓋現有資料）──────────
# ⛔ 破壞性操作，先確認 mongo.pre.gz 可讀，見「備份與還原」
```

**回滾決策點**：部署後 10 分鐘內驗證清單未全過即回滾。

### 服務一覽

| 服務 | 映像 | 說明 |
|---|---|---|
| `nginx` | nginx:1.26-alpine | 反向代理，對外唯一入口（80 / 443） |
| `api` | 本地建置（python:3.13-slim） | Flask API，非 root 執行 |
| `worker` | 同 `api` image | Celery worker（含遊戲資料同步） |
| `beat` | 同 `api` image | Celery beat（排程） |
| `bot` | 同 `api` image | Discord bot |
| `mongo` | mongo:7 | 主檔 + 庫存 + 使用者 + 日誌 |
| `mysql` | mysql:8.0 | 選用 |
| `redis` | redis:7-alpine | Rate Limiting + Celery broker |

| 服務 | 網址 |
|---|---|
| 後台管理 | http://localhost/admin/ |
| Swagger UI | http://localhost/apidocs |
| 健康檢查 | http://localhost/ |

### 常用指令

```bash
docker compose ps                      # 各服務狀態
docker compose logs -f api             # Flask 日誌
docker compose logs -f worker          # Celery worker（同步進度看這裡）
docker compose logs -f bot             # Discord bot
docker compose exec api bash           # 進入容器
docker compose restart api             # 重啟 Flask（Python 程式碼異動後）
docker compose restart bot             # 重啟 bot（改了 bot/ 之後）
docker compose restart nginx           # 重載 nginx 設定
docker compose down                    # 停止所有服務（資料保留）
docker compose build --no-cache api    # 重新建置 Flask + Vue
```

---

## 域名部署（HTTPS）

nginx 模式透過 `.env` 的 `NGINX_MODE` 控制，不需手動換設定檔，改完重啟即可。

| `NGINX_MODE` | 說明 | 適用情境 |
|---|---|---|
| `http` | 純 HTTP（預設） | 本機、無域名、內網 |
| `cloudflare` | Cloudflare Origin CA SSL | 域名走 Cloudflare 代理 |
| `https-letsencrypt` | Let's Encrypt SSL | 自行管理憑證 |

### 模式一：HTTP（預設）

```env
NGINX_MODE=http
DOMAIN=_
```

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

Cloudflare Dashboard → **SSL/TLS → Origin Server → Create Certificate**，
選 RSA、有效期 15 年，複製 **Origin Certificate** 與 **Private Key**。

```bash
mkdir -p /etc/ssl/cloudflare

# ⛔ 若目錄已有憑證，先備份再覆寫 —— 覆蓋掉正在使用的私鑰會導致 nginx 起不來
[ -f /etc/ssl/cloudflare/origin.key ] && \
  cp -a /etc/ssl/cloudflare /etc/ssl/cloudflare.$(date +%Y%m%d%H%M).bak

nano /etc/ssl/cloudflare/origin.pem   # 貼上 Origin Certificate
nano /etc/ssl/cloudflare/origin.key   # 貼上 Private Key
chmod 600 /etc/ssl/cloudflare/origin.key
```

#### 4. 事前快照

```bash
cp .env .deploy/env.$(date +%Y%m%d%H%M).bak
```

#### 5. 更新 `.env` 並啟動

```env
NGINX_MODE=cloudflare
DOMAIN=your.domain.com
CF_CERT_DIR=/etc/ssl/cloudflare
```

```bash
docker compose up -d
```

#### 6. 驗證清單

```bash
docker compose ps nginx                                  # Up (healthy)
docker compose exec nginx nginx -t                       # 設定語法正確
curl -fsI https://your.domain.com/ | head -1             # 200
curl -fs https://your.domain.com/ && echo                # ok
echo | openssl s_client -connect your.domain.com:443 \
  -servername your.domain.com 2>/dev/null | \
  openssl x509 -noout -dates                             # 憑證有效期
```

#### 7. 回滾

```bash
cp .deploy/env.<timestamp>.bak .env      # NGINX_MODE 回到 http
docker compose up -d nginx
curl -fs http://<伺服器IP>/ && echo      # 確認服務恢復
# 憑證有備份的話：rm -rf /etc/ssl/cloudflare && mv /etc/ssl/cloudflare.<ts>.bak /etc/ssl/cloudflare
```

> Cloudflare SSL/TLS 模式記得設為 **Full (Strict)**，確保端對端加密。

---

## 主機 nginx 部署

**適用情境**：主機上已安裝 nginx（或已有其他服務佔用 80/443），不想在 Docker 中再跑一個 nginx。

```
使用者 → 主機 nginx:80/443 → 127.0.0.1:5000（Docker api 容器）→ 資料庫容器
```

### Step 1：準備 no-nginx compose 檔

```bash
cp docker-compose.no-nginx.yml.sample docker-compose.no-nginx.yml
cp .env.default .env
cp conf/config.ini.default conf/config.ini
```

> 此檔已將 `api` 的 port 綁定為 `127.0.0.1:5000`，只讓主機 nginx 連入，不直接對外暴露。

調整 `conf/config.ini` 的主機名稱（同 Docker 部署 Step 2）。

### Step 2：安裝 nginx（Ubuntu / Debian）

```bash
sudo apt update && sudo apt install -y nginx
sudo systemctl enable --now nginx
```

### Step 3：事前快照

```bash
sudo mkdir -p /root/nginx-backup
sudo cp -a /etc/nginx/sites-available /root/nginx-backup/sites-available.$(date +%Y%m%d%H%M)
sudo cp -a /etc/nginx/sites-enabled   /root/nginx-backup/sites-enabled.$(date +%Y%m%d%H%M)
```

### Step 4：建立站台設定

```bash
# ── 模式一：HTTP ────────────────────────────────────────────────
sudo cp conf/nginx/host/http.conf /etc/nginx/sites-available/sc-tool
sudo nano /etc/nginx/sites-available/sc-tool
# 將 YOUR_DOMAIN 改為實際域名，或改為 _ 接受所有請求

# ── 模式二：Cloudflare Origin CA SSL ──────────────────────────
# 前置：建立 Cloudflare 憑證（見上方模式二）
sudo cp conf/nginx/host/cloudflare.conf /etc/nginx/sites-available/sc-tool
sudo nano /etc/nginx/sites-available/sc-tool     # YOUR_DOMAIN 共 2 處

# ── 模式三：Let's Encrypt SSL ──────────────────────────────────
sudo apt install -y certbot python3-certbot-nginx
# 先用模式一啟動 nginx，再申請憑證：
sudo certbot certonly --nginx -d your.domain.com
sudo cp conf/nginx/host/https-letsencrypt.conf /etc/nginx/sites-available/sc-tool
sudo nano /etc/nginx/sites-available/sc-tool     # YOUR_DOMAIN 共 4 處
```

> 三個範本檔的 log 路徑都寫死為 `/var/log/nginx/flask-app-{access,error}.log`。
> 要改成別的名稱請一併編輯 conf 檔內的 `access_log` / `error_log` 兩行。

### Step 5：啟用站台並重載

```bash
sudo ln -sf /etc/nginx/sites-available/sc-tool /etc/nginx/sites-enabled/sc-tool
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t                        # 語法錯誤就停在這裡，不要 reload
sudo systemctl reload nginx          # reload 不中斷連線，優先用這個
```

### Step 6：啟動 Docker 容器

```bash
docker compose -f docker-compose.no-nginx.yml up -d --build
```

### Step 7：驗證清單

```bash
sudo nginx -t                                        # 設定語法正確
systemctl is-active nginx                            # active
docker compose -f docker-compose.no-nginx.yml ps     # api 為 Up (healthy)
curl -fs http://127.0.0.1:5000/ && echo              # 容器直連 → ok
curl -fs http://your.domain.com/ && echo             # 經 nginx → ok
sudo tail -5 /var/log/nginx/flask-app-error.log      # 無新錯誤
```

### Step 8：回滾

```bash
sudo rm -f /etc/nginx/sites-enabled/sc-tool
sudo cp -a /root/nginx-backup/sites-enabled.<timestamp>/. /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
docker compose -f docker-compose.no-nginx.yml down
```

### 常用指令

```bash
sudo nginx -t                                        # 驗證設定語法
sudo systemctl reload nginx                          # 重載（不中斷連線）
sudo tail -f /var/log/nginx/flask-app-error.log      # 錯誤日誌
sudo tail -f /var/log/nginx/flask-app-access.log     # 訪問日誌
sudo certbot renew --dry-run                         # 測試自動續約
```

---

## 遊戲資料同步

物品 / 載具 / 商品主檔由 `tasks/scdata_sync.py` 從社群 API 同步而來。

| 排程 | 時間 | 內容 |
|---|---|---|
| `scdata-sync-daily` | 每日 04:30（Asia/Taipei） | items + vehicles + commodities + UEX |

**遊戲改版後手動觸發**比等排程實在：

```bash
docker compose exec worker python -c \
  "from tasks.scdata_sync import sync_scdata; print(sync_scdata())"

# 只同步物品
docker compose exec worker python -c \
  "from tasks.scdata_sync import sync_scdata; print(sync_scdata(resources=['items']))"

# 跳過 UEX
docker compose exec worker python -c \
  "from tasks.scdata_sync import sync_scdata; print(sync_scdata(with_uex=False))"
```

同步狀態：`GET /item/sync-status`，或直接查 `sync_runs` collection。

### Collections

| Collection | `_id` | 筆數（4.9） | 說明 |
|---|---|---|---|
| `item_master` | 遊戲 uuid | ~12,300 | 物品主檔（武器、裝備、船零件、塗裝） |
| `item_master_versions` | `uuid@version` | 累積 | 每個 patch 的唯讀快照 |
| `vehicle_master` | 遊戲 uuid | ~290 | 載具，含 SCU 容量與置物容器 |
| `commodity_master` | 遊戲 uuid | ~205 | 貨物，含可用箱體規格 |
| `uex_items` / `uex_items_prices` / `uex_terminals` | UEX id | — | 價格與終端（需 token） |
| `sync_runs` | run uuid | — | 每輪同步的統計與錯誤 |
| `inventory` | ObjectId | — | 庫存 |
| `inventory_log` | ObjectId | — | 異動稽核日誌 |
| `discord_bindings` | ObjectId | — | Discord ID ↔ RSI handle |

### 三個關鍵設計

**永不刪除。** 舊 patch 移除的物品不會從 DB 消失，只標成 `is_current: false` 並記錄
`retired_at`。庫存紀錄的 `item_id` 外鍵因此不會斷。**查主檔時記得加 `is_current: true`。**

**版本快照。** 每個 patch 各留一份 `*_versions`（`_id` 是 `uuid@version`，只在首次見到時
寫入）。要比對 4.8 → 4.9 之間某個零件的數值變動時查這裡。

**單位陷阱。** `volume_uscu` 是 **µSCU**（1 SCU = 1,000,000 µSCU），載具的
`cargo_capacity_scu` 已經是 SCU，`vehicle_inventory_uscu` 又是 µSCU。程式裡一律用
`uscu_to_scu()` 換算，不要自己除。

### 主檔文件長相

常查欄位拉平到頂層方便建索引，原始 API 回應整包留在 `raw`：

```javascript
{
  _id: "7b21462f-b0ad-433e-9809-d1a97f9e511e",   // 遊戲 uuid，外鍵用這個
  class_name: "Paint_100i_LunarNewYears2954_Red_Gold_Dog",
  name: "100i 2954 Auspicious Red Dog Livery",
  name_lower: "100i 2954 auspicious red dog livery",  // 前綴查詢走索引用
  type: "Paints",
  size: 1,
  volume_uscu: 24000,                            // µSCU
  manufacturer_code: "ORIG",
  game_version: "4.9.0-LIVE.12232306",
  is_current: true,
  raw: { /* 完整 API 回應 */ }
}
```

### Inventory schema

```javascript
{
  scope_id: "default",        // = WMS_SCOPE_ID，Web 與 bot 要一致
  owner_type: "guild",        // "guild" = 公會共享庫，"player" = 個人庫
  player: null,               // owner_type="player" 時是 RSI handle
  location: "Area18",
  container: "Box A",         // 可為 null
  item_id: "7b21462f-...",    // → item_master._id
  quantity: 42,
  updated_by: "TomLi",
  updated_at: ISODate("...")
}
```

`(scope_id, owner_type, player, location, container, item_id)` 是 unique index ——
同一儲位的同物品只會有一筆，入庫是 `$inc` 累加而不是新增。

### 併發與一致性

出庫用 `{quantity: {$gte: n}}` 當 filter 配 `$inc`，是單一原子操作 ——
兩個人同時出庫不會扣成負數，後到的會收到「庫存不足」。

移庫要動兩份文件，但**本專案的 mongo 是獨立節點，不支援多文件交易**。做法是補償式的：
先扣來源（原子且有數量保護），再加目的地，加失敗就把來源補回去。補償也失敗會留一筆
`action: "move_rollback_failed"` 的日誌供人工對帳。

要嚴格交易保證的話，把 mongo 改成單節點 replica set（`--replSet rs0` +
`rs.initiate()`，連線字串加 `?replicaSet=rs0&directConnection=true`），
再把 `Inventory.move()` 包進 session。

---

## Discord bot

### 指令

| 指令 | 說明 |
|---|---|
| `/bind <handle>` | 綁定 RSI handle，操作個人庫前必做 |
| `/unbind` · `/whoami` | 解除綁定 / 看綁定狀態與資料同步時間 |
| `/stock [scope] [location] [item]` | 查庫存，有上下頁按鈕 |
| `/find <query>` | 搜物品主檔（遊戲裡有哪些物品，不是庫存） |
| `/where <item>` | 這個物品都放在哪 |
| `/capacity [location] [scope] [ship]` | 算佔用 SCU，帶 `ship` 會比對船艙裝不裝得下 |
| `/price <item>` | 查在哪買賣、多少 aUEC |
| `/add` · `/remove` · `/move` | 入庫 / 出庫 / 移庫 |
| `/history [limit]` | 最近異動紀錄 |

物品與位置都有 autocomplete，選項的 value 是遊戲 uuid，所以指令收到的一定是明確主鍵。

### 建立 bot

1. [Developer Portal](https://discord.com/developers/applications) → New Application
2. **Bot** → Reset Token → 填入 `.env` 的 `DISCORD_TOKEN`
3. **Installation** → Guild Install，Scopes 勾 `applications.commands` 與 `bot`，
   Permissions 只需 `Send Messages` 和 `Embed Links`
4. 用產生的連結邀請 bot 進伺服器
5. 開發者模式下右鍵伺服器 → 複製伺服器 ID → 填 `DISCORD_GUILD_ID`

不需要 Message Content Intent —— 全部走斜線指令。

### 權限與可見性

| | 誰能寫 | 回覆可見性 |
|---|---|---|
| 公會共享庫 | `WMS_OPERATOR_ROLE` 角色，或有 Manage Server 權限的人 | 公開 |
| 個人庫 | 只有本人 | ephemeral（只有自己看得到） |

`WMS_OPERATOR_ROLE` 留空 = 所有人都能動公會庫。所有異動都寫進 `inventory_log`，
記錄操作者的 Discord ID 與 RSI handle。

### Web 與 bot 的分工

- **Web** = 管理主控台。可操作任何歸屬，但寫入需 `admin` / `operator` 角色。
- **Discord** = 玩家自助介面。玩家動自己的個人庫，公會庫需要 operator 角色。

兩邊共用 `src/models/inventory.py`，`WMS_SCOPE_ID` 相同就是同一份庫存。

---

## API 說明

### 公開端點

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/` | 健康檢查 |
| POST | `/auth/login` | 登入，回傳 JWT token |
| GET | `/admin/` | 後台管理 UI |
| GET | `/apidocs/` | Swagger UI（少斜線會 308 轉址） |

### 使用者管理（需 `Authorization: Bearer <token>`）

| 方法 | 路徑 | 所需角色 | 說明 |
|---|---|---|---|
| GET / POST | `/user/` | admin | 列出 / 新增使用者 |
| PUT / DELETE | `/user/<id>` | admin | 更新 / 刪除 |
| GET | `/log/` | 已登入 | 操作紀錄 |

### 遊戲主檔（唯讀，需登入）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/item/` | 物品列表（`?type=` 過濾） |
| GET | `/item/search?q=` | 名稱搜尋（前端 autocomplete 用） |
| GET | `/item/types` | 所有物品類型 |
| GET | `/item/<uuid>` | 單一物品（`?with_raw=1` 附原始回應） |
| GET | `/item/<uuid>/prices` | 在哪買賣、多少錢 |
| GET | `/item/vehicles` | 載具列表（含 SCU 貨艙容量） |
| GET | `/item/commodities` | 商品列表（含箱體規格） |
| GET | `/item/sync-status` | 資料同步狀態與遊戲版本 |

### 庫存

| 方法 | 路徑 | 所需角色 | 說明 |
|---|---|---|---|
| GET | `/inventory/` | 已登入 | 查庫存（`?owner_type=&player=&location=&item_id=`） |
| GET | `/inventory/locations` | 已登入 | 已使用過的位置清單 |
| GET | `/inventory/where/<uuid>` | 已登入 | 某物品在所有位置的分布 |
| GET | `/inventory/capacity` | 已登入 | 算佔用 SCU（`?ship=` 比對船艙） |
| GET | `/inventory/history` | 已登入 | 異動紀錄 |
| POST | `/inventory/add` | admin / operator | 入庫 |
| POST | `/inventory/remove` | admin / operator | 出庫 |
| POST | `/inventory/move` | admin / operator | 移庫 |

### 範例

```bash
TOKEN=$(curl -s -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .token)

# 搜尋物品
curl -s "http://localhost/item/search?q=agricium" -H "Authorization: Bearer $TOKEN"

# 入庫
curl -s -X POST http://localhost/inventory/add \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"item":"Agricium","quantity":50,"location":"Area18"}'

# 算 Freelancer MAX 裝不裝得下
curl -s "http://localhost/inventory/capacity?location=Area18&ship=Freelancer%20MAX" \
  -H "Authorization: Bearer $TOKEN"
```

`item` 欄位可以給遊戲 uuid 或完整名稱。名稱對到多筆時會回 400 要求改用 uuid。

**回應格式**：一律 `{"success": bool, "message"?: str, "data"?: any}`。
庫存不足、找不到物品這類預期錯誤回 400 並在 `message` 給可直接顯示的中文說明。

---

## 備份與還原

### RPO / RTO 目標

| 系統 | 內容 | RPO（最多可丟資料） | RTO（最多可停機） |
|---|---|---|---|
| MongoDB | 使用者、庫存、稽核日誌 | ≤ 24 小時 | ≤ 1 小時 |
| MongoDB（主檔部分） | 遊戲主檔 | 不適用（可重新同步取得） | ≤ 2 小時（重跑同步） |
| MySQL | 選用功能 | ≤ 24 小時 | ≤ 1 小時 |
| Redis | Rate Limit 計數 + Celery queue | 全部可丟，屬預期 | ≤ 15 分鐘 |

主檔可以重新同步，庫存與稽核日誌不行 —— **備份的重點是 `inventory`、`inventory_log`、
`users`、`discord_bindings`**。

### 備份

```bash
mkdir -p backup

# MongoDB 全庫
docker compose exec -T mongo mongodump --archive --db=flask_app --gzip \
  > backup/mongo-$(date +%Y%m%d%H%M).gz

# 只備份不可重建的 collection（快很多，日常用這個）
docker compose exec -T mongo mongodump --archive --gzip --db=flask_app \
  --collection=inventory > backup/inventory-$(date +%Y%m%d%H%M).gz
docker compose exec -T mongo mongodump --archive --gzip --db=flask_app \
  --collection=inventory_log > backup/inventory_log-$(date +%Y%m%d%H%M).gz
docker compose exec -T mongo mongodump --archive --gzip --db=flask_app \
  --collection=users > backup/users-$(date +%Y%m%d%H%M).gz

# MySQL
docker compose exec -T mysql sh -c \
  'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction flask_app' \
  | gzip > backup/mysql-$(date +%Y%m%d%H%M).sql.gz

# 設定檔（含 SECRET_KEY，請與資料備份同等保護）
tar czf backup/conf-$(date +%Y%m%d%H%M).tar.gz conf/config.ini conf/flask.json .env
```

**備份不等於可還原。** 驗證備份檔可讀：

```bash
docker compose exec -T mongo sh -c 'mongorestore --archive --gzip --dryRun' \
  < backup/mongo-<timestamp>.gz
```

### 還原

```bash
# ⛔ --drop 會先清掉現有 collection，不可逆。確認你要的是還原而不是合併。
docker compose exec -T mongo mongorestore --archive --gzip --drop \
  < backup/mongo-<timestamp>.gz

# 單一 collection
docker compose exec -T mongo mongorestore --archive --gzip --drop \
  --nsInclude='flask_app.inventory' < backup/inventory-<timestamp>.gz

# MySQL
gunzip -c backup/mysql-<timestamp>.sql.gz | docker compose exec -T mysql sh -c \
  'mysql -u root -p"$MYSQL_ROOT_PASSWORD" flask_app'

# 還原後驗證
docker compose restart api worker bot
curl -fs http://localhost/ && echo
docker compose exec -T mongo mongosh flask_app --quiet --eval \
  'print("inventory:", db.inventory.countDocuments({}),
         "logs:", db.inventory_log.countDocuments({}),
         "users:", db.users.countDocuments({}))'
```

主檔壞掉不用還原，重跑同步就好（見[遊戲資料同步](#遊戲資料同步)）。

### 還原演練

**每 90 天至少一次**：取最近的備份，在非正式環境還原並驗證資料可查。

合格標準 = 在 RTO 內完成還原 **且** 資料落差 ≤ RPO。任一超標就要檢討備份頻率或流程。

| 演練日期 | 備份檔時間 | 還原耗時 | 資料落差 | 結果 |
|---|---|---|---|---|
| _(待填)_ | | | | |

---

## 危險操作清單

以下操作不可逆或會造成服務中斷。執行前務必先做[事前快照](#5-回滾)，
正式環境請先取得負責人同意。

| ⛔ 操作 | 後果 | 執行前必做 |
|---|---|---|
| `docker compose down -v` | **刪除所有資料庫 volume，資料全失** | 完整 mongodump + mysqldump 並驗證可讀 |
| `mongorestore --drop` | 覆蓋現有 collection | 先備份現況，確認要還原而非合併 |
| `db.<collection>.drop()` / `deleteMany()` | 資料永久消失 | 先 `mongodump --collection` |
| MySQL DDL（`ALTER` / `DROP TABLE`） | 可能鎖表或遺失欄位 | `mysqldump --single-transaction` |
| 覆寫 `origin.key` / `origin.pem` | nginx 起不來，服務中斷 | `cp -a` 備份整個憑證目錄 |
| `certbot certonly --force-renewal` | 觸及 Let's Encrypt 速率限制（每週 5 次） | 先 `--dry-run` |
| 換掉 `conf/flask.json` 的 `SECRET_KEY` | 所有既有 JWT / session 立即失效 | 確認可接受全員重新登入 |
| 刪除或覆蓋 backup 目錄的檔案 | 失去還原能力 | 只新增與驗證，不刪除 |
| `docker compose up -d` 於正式環境（未快照） | 出事無法回滾 | 先做事前快照 |
| 調高 `REQUEST_DELAY=0` 或加大 page size | 可能被社群 API 封鎖來源 IP | 不要做 |
| `systemctl restart nginx`（正式） | 中斷既有連線 | 優先用 `reload` |

### 變更凍結

以下期間禁止非緊急的正式環境變更：

- 還原演練進行中
- 已知外部服務異常期間（Git 託管、雲供應商、社群 API 事故）

---

## 設定檔說明

### conf/config.ini

| 區塊 | 參數 | 說明 |
|---|---|---|
| `[LOG]` | `LOG_DISABLE` / `LOG_PATH` / `LOG_LEVEL` / `LOG_FILE_DISABLE` | 日誌開關、路徑、等級 |
| `[SETTING]` | `FLASK_JSON_PATH` / `ADMIN_TITLE` | flask.json 路徑、後台頁面名稱 |
| `[GUNICORN]` | `WORKERS` / `BIND` / `TIMEOUT` / `WORKER_CLASS` … | WSGI 參數（見檔內註解） |
| `[MONGO]` | `MONGO_URI` / `MONGO_DB` | MongoDB 連線 |
| `[MYSQL]` | `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | MySQL 連線 |
| `[REDIS]` | `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis 連線 |
| `[SCDATA]` | `WIKI_API_BASE` / `UEX_API_BASE` | 社群 API base URL |
| | `REQUEST_DELAY` | 請求間隔秒數（預設 0.25，**不要調到 0**） |
| | `HTTP_TIMEOUT` / `MAX_RETRIES` / `BULK_SIZE` | 逾時、重試次數、批次大小 |
| | `PAGE_SIZE_ITEMS` / `PAGE_SIZE_VEHICLES` / `PAGE_SIZE_COMMODITIES` | 每頁筆數。載具單筆約 40KB，**不要調大** |
| | `USER_AGENT` | **請改成能聯絡到你的資訊** |

各參數的預設值與說明見 `conf/config.ini.default` 的行內註解。
機密值（`UEX_API_TOKEN`、`DISCORD_TOKEN`）只放 `.env`，不寫進 `config.ini`。

### .env

欄位清單見[環境事實 › `.env` 欄位清單](#env-欄位清單)。

### conf/flask.json

```json
{ "SECRET_KEY": "" }
```

留空時 `run.py` 啟動會自動產生並寫入。此檔不納入版控，但**屬於機密**，
備份時請與資料備份同等保護。

---

## 擴充模組教學

以新增「商品管理」模組為例。

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
    data = request.get_json() or {}
    return jsonify({'success': True}), 201
```

### 步驟二：建立 Model

商業邏輯放 model，不要寫在 view —— view 只負責解析參數與組回應。
這樣邏輯才能被 Discord bot 或 Celery 任務重用（`src/models/inventory.py` 就是這樣被兩邊共用的）。

```python
# src/models/product.py
from datetime import datetime
from src.mongo import get_db


class Product:
    COLLECTION = 'products'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def find_all(cls) -> list:
        return list(cls._col().find({}, {'_id': 0}))

    @classmethod
    def create(cls, name: str, price: float) -> str:
        result = cls._col().insert_one({
            'name': name, 'price': price, 'created_at': datetime.utcnow()
        })
        return str(result.inserted_id)
```

MySQL 用 `from src.mysql import query, execute`；Redis 快取用 `from src.redis_client import get_redis`。

### 步驟三：註冊藍圖與索引

```python
# app/__init__.py
from app.product.view import app_product

def create_app(config_object=None):
    ...
    app.register_blueprint(blueprint=app_product, url_prefix='/product')
```

```python
# src/mongo.py 的 ensure_indexes()
db['products'].create_index('name', unique=True)
```

### 步驟四：（選用）Swagger 文件

直接寫在 docstring 的 `---` 之後（見 `app/item/view.py`），或用 `@swag_from` 指向 yaml。

### 步驟五：寫測試

`tests/conftest.py` 已備好 mongomock / fakeredis / 停用的 limiter，
以及 `client`、`auth_headers`、`seed_admin` 等 fixture。

```python
def test_create_product(client, auth_headers):
    resp = client.post('/product/', headers=auth_headers, json={'name': 'x', 'price': 1})
    assert resp.status_code == 201
```

### 角色說明

| 角色 | 可存取範圍 |
|---|---|
| `admin` | 完整權限（含使用者管理、庫存異動） |
| `operator` | 一般操作 + 庫存異動（不可管理使用者） |
| `viewer` | 唯讀 |

```python
@require_role('admin')              # 僅 admin
@require_role('admin', 'operator')  # admin 或 operator
```

### 寫入操作紀錄

```python
from src.models.log import Log
from flask_jwt_extended import get_jwt_identity

Log.create(username=get_jwt_identity(), action='create_product',
           detail=f'name={name}', success=True)
```

---

## 注意事項

| 項目 | 說明 |
|---|---|
| `conf/flask.json` | 首次啟動自動產生，已 gitignore，**勿提交版控**；屬機密，備份要保護 |
| `conf/config.ini` | 由 `.default` 複製而來，已 gitignore |
| `docker-compose.yml` | 由 `.default` 複製而來，已 gitignore |
| `app/static/admin/` | Vue build 輸出，已 gitignore（Docker build 時自動產生） |
| 環境變數密碼 | `.env` 中的密碼均為公開的範本預設值，**正式環境務必修改** |
| 預設帳號 | `admin / admin`，**首次啟動後立即修改** |
| Rate Limiting | `/auth/login` 10 次/分鐘，`/auth/refresh` 30 次/分鐘（Redis 跨 worker 共享） |
| MAX_CONTENT_LENGTH | 請求 body 上限 16 MB，超過回 `413` |
| MongoDB Index | 啟動時自動建立（`src/mongo.py` 的 `ensure_indexes()`） |
| debug 模式 | 預設 `TestingConfig`，正式部署請改用 `ProductionConfig` |
| MySQL / Redis | Redis 為必要（Rate Limit + Celery）；MySQL 目前選用 |
| 資料庫 port | 三個資料庫都不對主機映射，要連線一律走 `docker compose exec` |
| MongoDB 交易 | 獨立節點不支援多文件交易，移庫是補償式的（見[併發與一致性](#併發與一致性)） |
| 第一輪同步 | 主檔是空的時候 autocomplete 沒有結果，先跑一次同步 |
| UEX 欄位名稱 | `src/scdata.py` 的 `UEX_RESOURCES` 依官方文件撰寫，未經實測。第一次拿到 token 同步後請 `db.uex_items.findOne()` 確認 |

---

## AI 協作制度

本專案遵循 `ai-governance` 的協作制度文件（同一 Git 帳號下另一個 repo）。
交給 AI 執行任務前，相關規範重點：

| 文件 | 與本專案的關聯 |
|---|---|
| `F_權限與危險操作邊界` | 執行任何指令前先對照。本 README 的[危險操作清單](#危險操作清單)是專案化的版本 |
| `G_環境事實檔` | 環境資訊一律查 G，不重新探索。本 README 的[環境事實](#環境事實)一節對應此文件 |
| `H_變更管理與回滾規範` | **寫不出回滾步驟的變更不准執行。** 本 README 每個部署流程都附事前快照、驗證清單、回滾步驟 |
| `E_事故處置手冊` | 告警時第一個打開的檔案 |
| `D_任務交辦模板` | 交辦任務前複製填空；變更／部署類用 H 第 1 章的變更單 |
| `L_CLAUDE_md規範` | 要往 `CLAUDE.md` 加東西之前先看 |

三條與本專案最相關的鐵律：

1. **動正式環境前先開變更單**，回滾欄空白的單一律無效。
2. **驗證清單全過才算完成**，不接受「理論上會過」；任一項不過就依回滾決策點回滾，不現場 debug。
3. **環境事實有變動**（換版本、開 port、換金鑰）時，當場更新本 README 的[環境事實](#環境事實)一節與 `G_環境事實檔`。

---

## 免責聲明

This is an unofficial Star Citizen fan tool, not affiliated with the Cloud Imperium group
of companies. All content not authored by its host or users are property of their
respective owners.

本專案為非官方星際公民粉絲工具，與 Cloud Imperium 集團無任何關聯。

Star Citizen®, Squadron 42®, Roberts Space Industries® and Cloud Imperium® are
registered trademarks of Cloud Imperium Rights LLC.

CIG 允許非商業的社群工具使用遊戲資料，條件是清楚標示非官方身分。對外可見的介面
（網頁、Discord embed、匯出檔案）都要帶上這段聲明 —— Discord bot 的每個 embed footer
已透過 `bot/ui.py` 的 `DISCLAIMER` 自動附帶。避免使用會讓人誤認為官方的網域或 logo；
商業化（收費、廣告）需另外向 CIG 申請授權。

### 資料來源

| 來源 | 用途 | 授權 |
|---|---|---|
| [Star Citizen Wiki API](https://api.star-citizen.wiki) | 物品 / 載具 / 商品規格 | [原始碼](https://github.com/StarCitizenWiki/API)，AGPL-3.0 |
| [UEX Corp](https://uexcorp.space) | 價格、終端與商店位置 | 社群眾包，可能與實際伺服器有落差 |
| [unp4k](https://github.com/dolkensp/unp4k) · [ScDataDumper](https://github.com/octfx/ScDataDumper) | 遊戲檔案解包工具（上游 API 使用） | — |

資料以遊戲檔案與社群回報為基礎，非即時抓取伺服器狀態。遊戲每次改版都可能造成數值變動，
請以遊戲內顯示為準。目前資料版本可查 `GET /item/sync-status`。
