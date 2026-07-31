"""推播通知發送介面。

此模組提供統一的 send_push() 介面，預設為 NotImplementedError。
依需求選擇實作方式：

  A. FCM（Android + iOS）
     pip install firebase-admin
     from firebase_admin import messaging, credentials, initialize_app
     初始化：initialize_app(credentials.Certificate('conf/firebase-key.json'))

  B. APNs（iOS 原生）
     pip install apns2
     使用 .p8 金鑰或 .pem 憑證

  C. 統一推播服務（Expo Push / OneSignal）
     透過 HTTP API 呼叫，不需額外 SDK

範例（FCM）：
  def send_push(tokens, title, body, data=None):
      from firebase_admin import messaging
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
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> dict:
    """
    發送推播通知。

    Args:
        tokens:  目標裝置 token 清單（FCM token / APNs device token）
        title:   通知標題
        body:    通知內文
        data:    額外 payload（dict），可附帶自訂欄位

    Returns:
        {'success': int, 'failure': int}
    """
    raise NotImplementedError(
        '請在 src/push_notification.py 實作 FCM / APNs / 統一推播服務邏輯，'
        '並安裝對應套件（firebase-admin / apns2）。'
    )


def send_push_to_user(username: str, title: str, body: str, data: dict | None = None) -> dict:
    """查詢該使用者所有裝置 token 並發送推播。"""
    from src.models.device_token import DeviceToken
    tokens = [t['token'] for t in DeviceToken.find_by_username(username)]
    if not tokens:
        logger.info('send_push_to_user: no tokens for %s', username)
        return {'success': 0, 'failure': 0}
    return send_push(tokens, title, body, data)
