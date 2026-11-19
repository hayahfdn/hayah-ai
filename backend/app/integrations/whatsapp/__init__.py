"""Official WhatsApp Business Cloud API (Meta) for the dedicated intake number.

Only webhook parsing, signature checks and media download live here. The
existing groups are not read by this system (the Cloud API cannot read
existing groups); the team forwards messages to the intake number, tagging
them with the group letter, e.g. "#B 1339 تم التسليم".
"""
import hashlib
import hmac
from datetime import datetime, timezone

import httpx

from app.config import get_settings


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_webhook(payload: dict) -> list[dict]:
    """Flatten a Cloud API webhook into simple message dicts. Status callbacks are skipped."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            to_id = (value.get("metadata") or {}).get("phone_number_id")
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                mtype = m.get("type", "text")
                text = None
                media = []
                if mtype == "text":
                    text = (m.get("text") or {}).get("body")
                elif mtype in ("image", "video", "document", "audio", "sticker"):
                    part = m.get(mtype) or {}
                    text = part.get("caption")
                    media.append({"id": part.get("id"), "mime_type": part.get("mime_type"), "sha256": part.get("sha256"),
                                  "filename": part.get("filename"), "type": mtype})
                elif mtype == "interactive":
                    i = m.get("interactive") or {}
                    text = ((i.get("button_reply") or i.get("list_reply") or {}).get("title"))
                ts = datetime.fromtimestamp(int(m.get("timestamp", 0) or 0), tz=timezone.utc)
                out.append({"external_id": m["id"], "sender_phone": m.get("from"), "sender_name": names.get(m.get("from")),
                            "received_at": ts, "message_type": mtype, "text": text, "media": media,
                            "forwarded": bool((m.get("context") or {}).get("forwarded")), "raw": m,
                            "to_phone_number_id": to_id})
    return out


class WaSendError(Exception):
    """transient=True: worth retrying (network, 5xx, rate limit). False: Meta refused it (wrong number, outside window...)."""
    def __init__(self, message: str, transient: bool = False, code: int | None = None):
        super().__init__(message)
        self.transient, self.code = transient, code


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        err = r.json().get("error") or {}
    except ValueError:
        err = {}
    code = err.get("code")
    msg = err.get("error_user_msg") or err.get("message") or r.text[:300]
    raise WaSendError(f"WhatsApp: {msg}" + (f" (code {code})" if code else ""), transient=r.status_code >= 500 or r.status_code == 429, code=code)


class CloudAPIClient:
    """Graph API calls. token / phone id / WABA id come from the server settings (never the browser)."""
    def __init__(self, token: str | None = None, phone_number_id: str | None = None, waba_id: str | None = None):
        s = get_settings()
        self.base = f"https://graph.facebook.com/{s.whatsapp_graph_version}"
        self.token = token if token is not None else s.whatsapp_access_token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.phone_number_id = phone_number_id or s.whatsapp_phone_number_id
        self.waba_id = waba_id

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        with httpx.Client(timeout=60) as c:
            meta = c.get(f"{self.base}/{media_id}", headers=self.headers)
            meta.raise_for_status()
            info = meta.json()
            blob = c.get(info["url"], headers=self.headers)
            blob.raise_for_status()
            return blob.content, info.get("mime_type", "application/octet-stream")

    def _post(self, path: str, **kw) -> dict:
        try:
            with httpx.Client(timeout=120) as c:
                r = c.post(f"{self.base}/{path}", headers=self.headers, **kw)
        except httpx.HTTPError as e:  # no answer from Meta: safe to retry (the message was not accepted)
            raise WaSendError(f"WhatsApp could not be reached: {e}", transient=True)
        _raise_for(r)
        return r.json()

    def send(self, payload: dict) -> str:
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", **payload}
        return self._post(f"{self.phone_number_id}/messages", json=body)["messages"][0]["id"]

    def upload_media(self, data: bytes, mime_type: str, filename: str) -> str:
        return self._post(f"{self.phone_number_id}/media", data={"messaging_product": "whatsapp", "type": mime_type},
                          files={"file": (filename, data, mime_type)})["id"]

    def mark_read(self, wa_message_id: str) -> None:
        try:
            self._post(f"{self.phone_number_id}/messages", json={"messaging_product": "whatsapp", "status": "read", "message_id": wa_message_id})
        except WaSendError:
            pass  # read receipts are best effort

    def templates(self) -> list[dict]:
        if not self.waba_id:
            return []
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{self.base}/{self.waba_id}/message_templates", headers=self.headers,
                      params={"fields": "name,language,status,category,components", "limit": 200})
        _raise_for(r)
        return r.json().get("data", [])

    def phone_info(self) -> dict:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{self.base}/{self.phone_number_id}", headers=self.headers,
                      params={"fields": "display_phone_number,verified_name,quality_rating,platform_type"})
        _raise_for(r)
        return r.json()


class MockWhatsAppClient:
    """Offline stand-in for tests and the demo: stores media by id and records what would be sent."""
    media: dict[str, tuple[bytes, str]] = {}
    sent: list[dict] = []
    fail_next: list[WaSendError] = []

    def __init__(self, *a, **kw):
        self.waba_id = kw.get("waba_id") or "mock-waba"

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        if media_id not in self.media:
            raise RuntimeError(f"Mock media {media_id} not found")
        return self.media[media_id]

    def send(self, payload: dict) -> str:
        if self.fail_next:
            raise self.fail_next.pop(0)
        import uuid
        wid = f"wamid.mock-{uuid.uuid4().hex[:16]}"
        self.sent.append({"id": wid, **payload})
        return wid

    def upload_media(self, data: bytes, mime_type: str, filename: str) -> str:
        import uuid
        mid = f"mockmedia-{uuid.uuid4().hex[:10]}"
        self.media[mid] = (data, mime_type)
        return mid

    def mark_read(self, wa_message_id: str) -> None:
        pass

    def templates(self) -> list[dict]:
        return [{"name": "hello_world", "language": "en_US", "status": "APPROVED", "category": "UTILITY",
                 "components": [{"type": "BODY", "text": "Hello World"}]},
                {"name": "order_update", "language": "ar", "status": "APPROVED", "category": "UTILITY",
                 "components": [{"type": "BODY", "text": "مرحباً {{1}}، تحديث بخصوص طلبك رقم {{2}}."}]}]

    def phone_info(self) -> dict:
        return {"display_phone_number": "+000 mock", "verified_name": "Mock", "platform_type": "CLOUD_API"}


_client = None


def get_whatsapp_client():
    """The client for the intake number (environment settings)."""
    global _client
    if _client is None:
        _client = CloudAPIClient() if get_settings().whatsapp_backend == "meta" else MockWhatsAppClient()
    return _client
