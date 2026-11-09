# AI 問答：免費額度輪換設計

Discord 機器人 `/ask` 指令用 AI 回答問題，答案根據網站自己的資料庫。
用多家免費 AI 服務輪流，一家額度用完或出錯就自動換下一家。

> 免費方案的額度常變動，下面的數字是 2026 年的大概值，實際以各家後台顯示為準。

---

## 1. 候選供應商

| 順位 | 服務 | 免費額度（大約） | 說明 |
|---|---|---|---|
| 1 | Google Gemini（AI Studio） | 每分鐘 5–15 次、每天數百到上千次（依模型） | 中文好、支援工具呼叫；**免費版內容會被拿去改進產品** |
| 2 | Groq | 每分鐘約 30 次、每天約 1,000 次 | 很快，開源模型（Llama 等） |
| 3 | Cerebras | 每分鐘約 30 次、每天約 100 萬 token | 很快 |
| 4 | OpenRouter 免費模型 | 每天約 50 次（儲值 10 美元後 1,000 次） | 一個 API 可換多種模型 |

原則：**不同供應商各一把 key**。同一家開多個帳號／多把 key 繞過免費額度多半違反服務條款，可能被停用。

---

## 2. 整體流程

```
Discord /ask 問題
   │
   ▼
bot/ ──► 後端 POST /ai/ask（帶玩家身分）
           │
           ▼
      AI 路由器（輪換）
           │  1. 依順序挑一家「沒在冷卻中」的供應商
           │  2. 送出：系統提示＋問題＋工具清單
           │  3. 失敗（429／5xx／逾時）→ 標記冷卻 → 換下一家重送
           ▼
      AI 回傳「要呼叫的工具＋參數」
           │
           ▼
      後端執行工具（查自己的資料庫）→ 結果交回 AI
           │（可以來回幾輪，設上限，例如 4 輪）
           ▼
      AI 用中文整理答案 ──► Discord 回覆
```

---

## 3. 輪換規則

| 狀況 | 處理 |
|---|---|
| 429（額度用完／限流） | 照回應的 `Retry-After` 冷卻；沒給就冷卻 60 秒；換下一家 |
| 當日額度用完 | 冷卻到隔天（UTC 0 點或該家的重置時間） |
| 5xx、連線錯誤、逾時（例如 20 秒） | 冷卻 30 秒，換下一家 |
| 4xx（key 錯、參數錯） | 標記「設定錯誤」，停用並在後台顯示，不自動重試 |
| 全部都在冷卻 | 回覆「AI 暫時忙碌，請稍後再試」 |

- 冷卻狀態放 Redis（專案已經有），多個 worker 共用：`ai:cooldown:<provider>` 設 TTL。
- 同一個問題途中換供應商時，從頭重送（不同家的工具呼叫格式不保證互通）。

---

## 4. 統一介面

各家大多支援 **OpenAI 相容 API**（`/chat/completions`＋`tools`），所以只寫一個呼叫介面：

```python
# src/ai/providers.py（示意）
PROVIDERS = [
    {'key': 'gemini',     'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai', 'model': '...'},
    {'key': 'groq',       'base_url': 'https://api.groq.com/openai/v1',                          'model': '...'},
    {'key': 'cerebras',   'base_url': 'https://api.cerebras.ai/v1',                              'model': '...'},
    {'key': 'openrouter', 'base_url': 'https://openrouter.ai/api/v1',                            'model': '...:free'},
]

def chat(messages, tools):
    for p in enabled_in_order():
        if in_cooldown(p):
            continue
        try:
            return call_openai_compatible(p, messages, tools, timeout=20), p['key']
        except RateLimited as e:
            cooldown(p, e.retry_after or 60)
        except (ServerError, Timeout):
            cooldown(p, 30)
        except ClientError:
            disable(p, reason='設定錯誤')
    raise AllBusy()
```

> base_url、模型名稱以各家文件為準，模型名稱放後台設定，不寫死。

---

## 5. 工具（AI 只能透過這些查資料）

直接包現有的查詢函式，**唯讀**，回傳精簡欄位：

| 工具名稱 | 用途 | 對應現有功能 |
|---|---|---|
| `find_item_holders(name, player?)` | 誰有某物品、放哪裡 | `/inventory/search` |
| `find_blueprint_holders(name, player?)` | 誰有某藍圖 | `Blueprint.find_holders` |
| `find_ship_holders(name, player?)` | 誰有某艘船（含公開的配件網址） | `Fleet.find_holders` |
| `player_summary(player)` | 某玩家的物品／藍圖／船艦 | 上面三個合併 |
| `item_info(name)` | 物品資料、哪裡買得到 | `/item/`、UEX 價格 |
| `commodity_where_to_buy(names[])` | 商品哪裡買得到 | 商品購買地點 |
| `mission_search(keyword)` | 任務、獎勵藍圖 | `/mission/` |

注意：
- 只開放玩家頁本來就看得到的資料（不公開的配件網址、密碼、token 一律不給）。
- 每個工具結果截短（例如最多 30 筆），避免吃光 token。

---

## 6. 系統提示（範例）

```
你是星際公民公會工具網站的助理，用繁體中文回答。
只根據工具查到的資料回答；查不到就說查不到，不要猜。
數量、地點、玩家名稱照工具結果原樣寫。
回答簡短，必要時用條列。
```

---

## 7. 後台設定（系統設定頁）

- 每家：啟用開關、API key、模型名稱、順位（拖拉排序）。
- 狀態：目前是否冷卻中、今日呼叫次數、失敗次數、最後錯誤訊息。
- API key 存 `app_settings`（同 UEX token），**資料備份會一起匯出，要保管好**。

---

## 8. Discord 端

- 指令：`/ask 問題`，回覆時先顯示「思考中…」再編輯成答案。
- 每人限流：例如每分鐘 3 次、每天 50 次（Redis 計數），避免少數人用光全公會的免費額度。
- 答案過長（Discord 單則 2,000 字）就截斷並附「到網站看完整結果」的連結（例如查詢持有資訊的分享網址）。
- 回覆最後標註是哪一家回答的（方便除錯，可關閉）。

---

## 9. 紀錄

每次問答記一筆（新集合 `ai_logs`）：時間、玩家、問題、用了哪一家、呼叫了哪些工具、耗時、成功／失敗。
後台可看用量統計，用來調整順位。設定保留天數（例如 30 天）自動清掉。

---

## 10. 隱私與風險

- 問題和查詢結果會送到 AI 供應商；免費方案多半會拿去改進產品（例如 Gemini 免費版）。
- 輪換＝多家供應商都看得到公會資料，要讓成員知道。
- 在意的話：改用付費方案（通常不拿去訓練），或自架 Ollama（不外流，但要主機夠力、品質較差）。

---

## 11. 建議實作順序

1. 後端 `src/ai/`：供應商設定、OpenAI 相容呼叫、輪換＋冷卻（Redis）。
2. 工具：先做 `find_item_holders`、`find_blueprint_holders`、`find_ship_holders`、`player_summary`。
3. `POST /ai/ask`（只給機器人／登入玩家用）＋ `ai_logs`。
4. Discord `/ask` 指令＋每人限流。
5. 後台設定與用量頁。
6. 先接 Gemini＋Groq 兩家，穩定後再加 Cerebras、OpenRouter。
7. 測試：輪換（模擬 429／逾時）、工具權限（不公開資料不外流）、限流。
