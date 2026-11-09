"""AI 問答（Discord /ask、後台測試）：用免費 AI 服務輪換回答問題，資料來自自己的資料庫。

- config.py：後台設定（啟用、供應商順序、API key、模型、每人限流），存在 app_settings 的 ai_config
- router.py：照順序呼叫供應商（OpenAI 相容 /chat/completions），被限流／出錯就冷卻並換下一家
- tools.py：AI 可以呼叫的查詢工具（唯讀；只給玩家頁本來就看得到的資料）
- ask.py：一次問答（AI ⇄ 工具來回最多幾輪）、紀錄（ai_logs）、每人限流

設計文件：docs/AI免費額度輪換設計.md
"""
