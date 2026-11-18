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
                            "forwarded": bool((m.get("context") or {}).get("forwarded")), "raw": m})
    return out


class CloudAPIClient:
    def __init__(self):
        s = get_settings()
        self.base = f"https://graph.facebook.com/{s.whatsapp_graph_version}"
        self.headers = {"Authorization": f"Bearer {s.whatsapp_access_token}"}

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        with httpx.Client(timeout=60) as c:
            meta = c.get(f"{self.base}/{media_id}", headers=self.headers)
            meta.raise_for_status()
            info = meta.json()
            blob = c.get(info["url"], headers=self.headers)
            blob.raise_for_status()
            return blob.content, info.get("mime_type", "application/octet-stream")


class MockWhatsAppClient:
    """Returns stored bytes for media ids registered by tests or the demo script."""
    media: dict[str, tuple[bytes, str]] = {}

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        if media_id not in self.media:
            raise RuntimeError(f"Mock media {media_id} not found")
        return self.media[media_id]


_client = None


def get_whatsapp_client():
    global _client
    if _client is None:
        _client = CloudAPIClient() if get_settings().whatsapp_backend == "meta" else MockWhatsAppClient()
    return _client
