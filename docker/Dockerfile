# ── Stage 1: 打包 Vue 3 前端 ────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

# 先複製 package.json + package-lock.json，利用 layer cache 加速 npm ci
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

# 複製其餘前端原始碼並打包
COPY frontend/ ./

# vite.config.js 的 outDir = '../web-admin'，對應到 /build/web-admin。
# 刻意輸出在 app/ 外面 —— app/ 在 docker-compose.api.yml 是 bind mount，
# 建置產物放在裡面會被 host 的目錄整個遮住（見 app/admin/view.py 的說明）。
RUN mkdir -p /build/web-admin && npm run build


# ── Stage 2: Python Flask App ────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# 安裝系統工具（curl 供 healthcheck 使用）
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴（利用 layer cache）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有程式碼
COPY . .

# 放入 Stage 1 打包好的後台前端。web-admin/ 不在任何 bind mount 之下，
# 所以這份就是實際被服務的版本。
COPY --from=frontend-builder /build/web-admin/ ./web-admin/

# 以非 root 使用者執行（最小權限原則）
RUN useradd -m -u 1001 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# 正式環境用 Gunicorn；開發時可改為 python run.py
CMD ["gunicorn", "-c", "gunicorn.py", "run:app"]
