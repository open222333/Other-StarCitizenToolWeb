# Template-PythonFlaskAPI — Claude Code 專案指令

## 專案概覽

Flask + Vue 3 全端模板，提供 JWT 身份驗證、角色權限、使用者管理後台、操作日誌、Rate Limiting、Celery 排程任務等開箱即用功能。

- **後端入口**：`run.py`（開發）、`gunicorn.py`（生產）
- **排程任務**：`celery_worker.py`（Celery Worker + Beat）
- **前端**：Vue 3 SPA，編譯後由 Flask 的 `/admin/` 路徑提供服務
- **資料庫**：MongoDB（使用者 / 日誌）、MySQL（可擴充）、Redis（Rate Limiting + Celery Broker）
- **部署**：Docker multi-stage build + docker-compose（nginx + app + worker + beat + mongo + mysql + redis）

## 目錄結構速查

```
Template-PythonFlaskAPI/
├── run.py              ← 開發入口（自動初始化 SECRET_KEY、admin 帳號）
├── gunicorn.py         ← 生產 WSGI 設定
├── celery_worker.py    ← Celery Worker / Beat 入口
├── requirements.txt    ← Python 依賴
├── conf/               ← 設定（config.ini、config.py、nginx/）
├── app/                ← Flask Blueprint 路由
│   ├── auth/           ← /auth/login, /auth/refresh, /auth/me
│   ├── user/           ← /user/ CRUD + /user/templates/ CRUD
│   ├── log/            ← /log/ 操作日誌
│   ├── admin/          ← /admin/ 靜態 SPA
│   ├── docs/           ← /docs/ 說明文件
│   └── sample/         ← /sample/ 範例路由
├── src/                ← 核心模組
│   ├── __init__.py     ← config.ini 讀取，匯出所有設定值
│   ├── mongo.py        ← MongoDB 連線 + ensure_indexes()
│   ├── mysql.py        ← MySQL 連線池
│   ├── redis_client.py ← Redis 連線
│   ├── limiter.py      ← Flask-Limiter（Redis 後端）
│   ├── celery_app.py   ← Celery 實例（Redis DB 1 作為 Broker）
│   ├── permissions.py  ← @require_role 裝飾器
│   └── models/         ← 資料模型（user, user_template, log）
├── tasks/              ← Celery 任務
│   ├── __init__.py     ← 匯入所有任務（讓 autodiscover 生效）
│   ├── celeryconfig.py ← Beat 排程設定（timezone、beat_schedule）
│   └── scheduled.py    ← 範例排程任務（日誌清理、健康檢查）
├── frontend/           ← Vue 3 前端原始碼
│   └── src/
│       ├── api/        ← API 呼叫工具（apiFetch + userApi + logApi）
│       ├── stores/     ← Pinia 狀態（auth, theme）
│       ├── views/      ← 頁面（Login, Users, Logs, Settings）
│       └── components/ ← 共用元件（UserModal, TemplateModal, ConfirmModal）
└── docker/             ← Dockerfile + 資料庫持久化目錄
```

---

## 架構擴充評估

| 擴充方向 | 難度 | 原因 |
|----------|------|------|
| 新增 API 模組 | **容易** | Blueprint pattern 清晰，照既有 6 個模組範例即可 |
| 新增 MongoDB 模型 | **容易** | `src/models/` 結構固定，照 user.py / log.py 複製 |
| 新增前端頁面 | **容易** | Vue Router + Pinia 已到位，照 views/ 範例複製 |
| 新增 MySQL 模型 | **容易** | `src/mysql.py` 已有 query/execute helpers |
| 新增排程任務 | **容易** | 在 `tasks/` 加任務檔，在 `celeryconfig.py` 加一行排程即可 |
| 新增角色（RBAC）| **中等** | 需改 `src/models/user.py` 的 ROLES + permissions.py |
| API 版本控制 | **中等** | 需建 `app/api/v1/` 結構並統一 Blueprint 前綴 |
| 新增背景任務 | **中等** | 需引入 Celery，Redis 已在位可直接作為 Broker |
| WebSocket | **較難** | 需換 Gunicorn worker class（gevent）並新增 SocketIO |

---

## 新增 API 模組

### 1. 建立 Blueprint 目錄

```
app/<feature>/
├── __init__.py   ← 空檔（讓 Python 識別為 package）
└── view.py       ← 路由定義
```

### 2. `app/<feature>/view.py` 範本

```python
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.permissions import require_role
from src.limiter import limiter
from src.models.log import Log

app_feature = Blueprint('app_feature', __name__)


@app_feature.route('/', methods=['GET'])
@jwt_required()
def list_feature():
    return jsonify({'success': True, 'data': []})


@app_feature.route('/', methods=['POST'])
@jwt_required()
@require_role('admin')
@limiter.limit('20 per minute')
def create_feature():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '缺少請求參數'}), 400

    username = get_jwt_identity()
    Log.create(username, 'create_feature', detail=str(data))
    return jsonify({'success': True}), 201
```

### 3. 在 `app/__init__.py` 註冊

```python
from app.feature.view import app_feature
# 在 create_app() 內加入：
app.register_blueprint(blueprint=app_feature, url_prefix='/feature')
```

### 4. 若有前端需求，在 `frontend/vite.config.js` 的 dev proxy 加入

```js
server: {
  proxy: {
    '/feature': 'http://localhost:5000',
    // ... 其他既有路徑
  }
}
```

---

## 新增 MongoDB 模型

```python
# src/models/feature.py
from datetime import datetime
from src.mongo import get_db


class Feature:
    COLLECTION = 'features'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def create(cls, name: str, **kwargs) -> str:
        result = cls._col().insert_one({
            'name': name,
            'created_at': datetime.utcnow(),
            **kwargs,
        })
        return str(result.inserted_id)

    @classmethod
    def find_all(cls) -> list:
        return list(cls._col().find({}, {'_id': 0}).sort('created_at', -1))
```

若需要索引，在 `src/mongo.py` 的 `ensure_indexes()` 加入：

```python
db['features'].create_index('name', unique=True)
db['features'].create_index([('created_at', DESCENDING)])
```

---

## 新增前端頁面

### 1. 建立 View 元件

```
frontend/src/views/FeatureView.vue
```

```vue
<template>
  <div>
    <h4>功能標題</h4>
    <!-- 頁面內容 -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const items = ref([])

onMounted(async () => {
  const res = await fetch('/feature/')
  if (res?.ok) items.value = (await res.json()).data
})
</script>
```

### 2. 在 `frontend/src/router/index.js` 加入路由

```js
{
  path: '/feature',
  name: 'Feature',
  component: () => import('@/views/FeatureView.vue'),
  meta: { requiresAuth: true }
}
```

### 3. 在 `DashboardLayout.vue` 側邊欄加入連結

```html
<li class="nav-item">
  <RouterLink to="/feature" class="nav-link">
    <i class="bi bi-star me-2"></i>功能名稱
  </RouterLink>
</li>
```

### 4. 若需要呼叫 API，在 `frontend/src/api/index.js` 加入

```js
export const featureApi = {
  list:   ()       => apiFetch('/feature/'),
  create: (data)   => apiFetch('/feature/', { method: 'POST', body: JSON.stringify(data) }),
  remove: (id)     => apiFetch(`/feature/${id}`, { method: 'DELETE' }),
}
```

---

## 新增排程任務（Celery）

### 1. 建立任務函式

```python
# tasks/my_tasks.py
import logging
from src.celery_app import celery_app
from src.mongo import get_db

logger = logging.getLogger(__name__)


@celery_app.task(name='tasks.my_tasks.do_something', bind=True, max_retries=3)
def do_something(self, param: str):
    """任務說明（一行）。"""
    try:
        # 實作邏輯
        logger.info('do_something: param=%s', param)
        return {'status': 'ok'}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

### 2. 在 `tasks/__init__.py` 匯入

```python
from tasks.my_tasks import do_something  # noqa: F401
```

### 3. 在 `tasks/celeryconfig.py` 加入排程（若需定期執行）

```python
from celery.schedules import crontab

beat_schedule['my-task-name'] = {
    'task': 'tasks.my_tasks.do_something',
    'schedule': crontab(hour=4, minute=30),   # 每天 04:30
    'kwargs': {'param': 'value'},
}
```

**常用 schedule 格式：**

| 格式 | 意義 |
|------|------|
| `60.0` | 每 60 秒 |
| `crontab(minute=0, hour='*/2')` | 每 2 小時整點 |
| `crontab(hour=3, minute=0)` | 每天 03:00 |
| `crontab(day_of_week=1, hour=9)` | 每週一 09:00 |

### 4. 手動觸發任務（從 API 呼叫）

```python
from tasks.my_tasks import do_something

# 非同步執行（不等結果）
do_something.delay(param='value')

# 非同步執行 + 等待結果（最多 30 秒）
result = do_something.apply_async(kwargs={'param': 'value'})
output = result.get(timeout=30)
```

### 5. 開發啟動

```bash
# Worker（執行任務）
celery -A celery_worker worker --loglevel=info

# Beat（定時觸發任務，另開終端）
celery -A celery_worker beat --loglevel=info
```

---

## 常用 Pattern

### 角色保護

```python
@require_role('admin')          # 只允許 admin
@require_role('admin', 'operator')   # 允許 admin 或 operator
```

角色層級：`admin (3)` > `operator (2)` > `viewer (1)`，定義在 `src/permissions.py`。

### Rate Limiting

```python
@limiter.limit('10 per minute')   # IP 限速
@limiter.limit('100 per hour')
```

限速使用 Redis 作為後端，跨 Gunicorn worker 共用計數，定義在 `src/limiter.py`。

### 操作日誌

```python
from src.models.log import Log
Log.create(username, 'action_name', detail='...', success=True)
```

前端可透過 `GET /log/?username=xxx&offset=0&limit=50` 查詢，支援分頁與使用者篩選。

### JWT Identity

```python
from flask_jwt_extended import jwt_required, get_jwt_identity

@jwt_required()
def my_endpoint():
    username = get_jwt_identity()   # 取得當前登入使用者名稱
```

---

## 開發環境

```bash
# 複製設定
cp conf/config.ini.default conf/config.ini
cp .env.default .env

# 啟動依賴服務
docker compose up -d mongo mysql redis

# 安裝 Python 依賴
pip install -r requirements.txt

# 啟動後端（port 5000，auto-reload）
FLASK_DEBUG=true python run.py

# 啟動 Celery Worker（另開終端）
celery -A celery_worker worker --loglevel=info

# 啟動 Celery Beat 排程器（另開終端）
celery -A celery_worker beat --loglevel=info

# 啟動前端開發伺服器（port 5173，含 proxy）
cd frontend && npm install && npm run dev
```

## 重要環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `FLASK_PORT` | `5000` | Flask 監聽 port |
| `FLASK_DEBUG` | `false` | `true` 啟用 debug mode（開發用） |
| `ADMIN_PASSWORD` | `admin` | 初始化 admin 帳號密碼 |
| `MYSQL_ROOT_PASSWORD` | — | MySQL root 密碼 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | — | MySQL 應用帳號 |
| `REDIS_PASSWORD` | — | Redis 密碼（Rate Limiting 必要） |
| `JWT_ACCESS_TOKEN_EXPIRES_HOURS` | `8` | JWT 存取 token 有效時間 |

詳見 `.env.default`。

---

## iOS / Android 行動端擴充

### 現有支援

| 功能 | 狀態 | 位置 |
|------|------|------|
| JWT 驗證（access + refresh token） | ✅ 已完成 | `app/auth/view.py` |
| CORS（Vite dev + 自訂域名，透過 CORS_ORIGIN 環境變數） | ✅ 已完成 | `app/__init__.py` |
| 裝置 token 登記 / 移除 | ✅ 已完成 | `app/device/view.py` |
| 推播通知介面（stub） | ✅ 架構完成，需實作 | `src/push_notification.py` |
| 裝置 token 180 天 TTL | ✅ 已完成 | `src/mongo.py` |

### 實作推播通知

**方式 A — FCM（Android + iOS）**

```bash
pip install firebase-admin
# 在 conf/ 放入 Firebase Service Account JSON
```

```python
# src/push_notification.py — 替換 send_push():
from firebase_admin import messaging, credentials, initialize_app

initialize_app(credentials.Certificate('conf/firebase-key.json'))

def send_push(tokens, title, body, data=None):
    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )
        for token in tokens
    ]
    response = messaging.send_each(messages)
    return {'success': response.success_count, 'failure': response.failure_count}
```

**方式 B — Expo Push（React Native 通用）**

```python
import requests

def send_push(tokens, title, body, data=None):
    messages = [{'to': t, 'title': title, 'body': body, 'data': data or {}} for t in tokens]
    r = requests.post('https://exp.host/--/api/v2/push/send', json=messages, timeout=10)
    return r.json()
```

### 從任務或 API 發送推播

```python
from src.push_notification import send_push_to_user

# 對單一使用者推播
send_push_to_user('alice', title='訂單已出貨', body='您的訂單 #1234 已出貨')

# 對指定 token 清單推播
from src.push_notification import send_push
from src.models.device_token import DeviceToken

tokens = [t['token'] for t in DeviceToken.find_by_platform('alice', 'ios')]
send_push(tokens, title='通知', body='內容')
```

### API 版本化（手機 App 必要）

手機 App 無法強迫使用者即時更新，舊版 App 可能繼續使用舊 API。
建議在需要 breaking change 時建立版本化路由：

```
app/
├── api/
│   ├── v1/
│   │   ├── __init__.py
│   │   └── user/view.py   ← 舊版邏輯維持不變
│   └── v2/
│       ├── __init__.py
│       └── user/view.py   ← 新版邏輯
```

```python
# app/__init__.py — create_app() 內加入
from app.api.v1.user.view import bp as user_v1
from app.api.v2.user.view import bp as user_v2
app.register_blueprint(user_v1, url_prefix='/api/v1/user')
app.register_blueprint(user_v2, url_prefix='/api/v2/user')
```

### 行動端登入 / 登出流程

```
App 啟動
  → POST /auth/login  → 取得 access_token + refresh_token
  → POST /device/register  → 送出 FCM/APNs token

Token 過期
  → POST /auth/refresh  → 取得新 access_token（refresh_token 30 天有效）

App 登出
  → POST /device/unregister  → 移除推播 token
  → 清除本機 token
```

---

## 已知技術債

| 項目 | 位置 | 建議 |
|------|------|------|
| Flask 2.2.3（舊版） | `requirements.txt` | 可升至 Flask 3.x，需確認 Flasgger 相容性 |
| Swagger 端點無需驗證 | `/apidocs` | 生產環境建議用 nginx 限制 `/apidocs` 存取 IP |
| `run.py` 使用 TestingConfig | `run.py` L34 | 新增 `FLASK_ENV` 判斷，自動切換 ProductionConfig |
| 日誌無 IP / User-Agent | `src/models/log.py` | 可在 `Log.create()` 加入 `request` context 擷取 |
| 無 CSP header | `app/__init__.py` | 加入後需測試 Swagger / Vue SPA 相容性再上線 |
