# 1. Gửi text message tới user (quan trọng nhất)

## Python (requests)

```python
import requests

ZALO_API_URL = "https://openapi.zalo.me/v2.0/oa/message"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

def send_text_message(user_id: str, text: str):
    headers = {
        "Content-Type": "application/json",
        "access_token": ACCESS_TOKEN,
    }

    payload = {
        "recipient": {
            "user_id": user_id
        },
        "message": {
            "text": text
        }
    }

    response = requests.post(ZALO_API_URL, json=payload, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Zalo API error: {response.text}")

    return response.json()
```

---

## Async (dùng cho FastAPI / worker)

```python
import httpx

ZALO_API_URL = "https://openapi.zalo.me/v2.0/oa/message"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

async def send_text_message_async(user_id: str, text: str):
    headers = {
        "Content-Type": "application/json",
        "access_token": ACCESS_TOKEN,
    }

    payload = {
        "recipient": {
            "user_id": user_id
        },
        "message": {
            "text": text
        }
    }

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(ZALO_API_URL, json=payload, headers=headers)

    if res.status_code != 200:
        raise Exception(f"Zalo API error: {res.text}")

    return res.json()
```

---

# 2. Webhook handler (FastAPI)

```python
from fastapi import APIRouter, Request
import json

router = APIRouter()

@router.post("/webhooks/zalo")
async def zalo_webhook(request: Request):
    body = await request.json()

    # Debug log
    print(json.dumps(body, indent=2))

    # Extract message
    message = body.get("message", {})
    sender = body.get("sender", {})

    user_id = sender.get("id")
    text = message.get("text")

    if text:
        print(f"[ZALO] {user_id}: {text}")

        # push vào queue thay vì xử lý trực tiếp
        # publish_to_queue(...)

    return {"success": True}
```

---

# 3. Lấy access token (OAuth flow)

## Exchange code → access token

```python
import requests

def get_access_token(app_id, app_secret, code):
    url = "https://oauth.zaloapp.com/v4/access_token"

    payload = {
        "app_id": app_id,
        "app_secret": app_secret,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(url, data=payload)

    if response.status_code != 200:
        raise Exception(response.text)

    return response.json()
```

---

## Refresh token

```python
def refresh_access_token(app_id, refresh_token):
    url = "https://oauth.zaloapp.com/v4/access_token"

    payload = {
        "app_id": app_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, data=payload)

    if response.status_code != 200:
        raise Exception(response.text)

    return response.json()
```

---

# 4. Gửi message có button (use sau Phase 1 nếu cần)

```python
def send_message_with_button(user_id: str):
    headers = {
        "Content-Type": "application/json",
        "access_token": ACCESS_TOKEN,
    }

    payload = {
        "recipient": {"user_id": user_id},
        "message": {
            "text": "Bạn muốn làm gì?",
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": "Chọn một hành động",
                    "buttons": [
                        {
                            "title": "Xem đơn hàng",
                            "type": "oa.query.show",
                            "payload": "#order"
                        },
                        {
                            "title": "Gặp nhân viên",
                            "type": "oa.query.show",
                            "payload": "#support"
                        }
                    ]
                }
            }
        }
    }

    res = requests.post(ZALO_API_URL, json=payload, headers=headers)
    return res.json()
```

---

# 5. Wrapper class (khuyên dùng)

```python
class ZaloClient:
    def __init__(self, access_token: str):
        self.base_url = "https://openapi.zalo.me/v2.0/oa/message"
        self.access_token = access_token

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "access_token": self.access_token,
        }

    def send_text(self, user_id: str, text: str):
        payload = {
            "recipient": {"user_id": user_id},
            "message": {"text": text}
        }

        res = requests.post(self.base_url, json=payload, headers=self._headers())

        if res.status_code != 200:
            raise Exception(res.text)

        return res.json()
```

---

# 6. Retry logic (rất quan trọng cho production)

```python
import time

def send_with_retry(client, user_id, text, retries=3):
    for attempt in range(retries):
        try:
            return client.send_text(user_id, text)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)

    raise Exception("Send failed after retries")
```

---

# 7. Mapping với Outbound Worker (your architecture)

```python
def handle_outbound_job(job):
    zalo = ZaloClient(access_token=job["access_token"])

    try:
        zalo.send_text(
            user_id=job["external_user_id"],
            text=job["messages"][0]["text"]
        )

        # save delivery success

    except Exception as e:
        # retry queue
        # save delivery failure
        pass
```

---

# 8. Những lỗi thường gặp (quan trọng)

## 1. Token hết hạn

→ cần refresh token hoặc cron refresh

## 2. Sai user_id

→ user chưa từng chat OA

## 3. Rate limit

→ cần retry + backoff

## 4. Gửi quá nhanh trong webhook

→ phải dùng queue (bạn đang làm đúng hướng)

## 5. Message format sai

→ Zalo khá strict JSON format

---

# 9. Best practice cho Phase 1

- KHÔNG gọi Zalo API trong webhook
- luôn qua queue + outbound worker
- wrap Zalo API thành 1 client riêng
- log full response JSON
- retry outbound
- lưu delivery_attempts vào DB
