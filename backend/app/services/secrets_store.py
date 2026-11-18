"""API keys an admin pastes in Settings, stored encrypted in the database.

The encryption key is derived from HAYAH_JWT_SECRET (which lives only in the
server's .env), so a database backup alone does not reveal the key. A key set
in the environment (HAYAH_ANTHROPIC_API_KEY) always wins. Keys are never sent
back to the browser; only the last 4 characters are shown.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

KEY = "secret.anthropic_api_key"


def _fernet() -> Fernet:
    raw = hashlib.sha256(("hayah-secrets:" + get_settings().jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def set_anthropic_key(db: Session, api_key: str | None, user_id: int | None) -> None:
    row = db.get(AppSetting, KEY)
    value = {"enc": _fernet().encrypt(api_key.encode()).decode(), "last4": api_key[-4:]} if api_key else {}
    if row:
        row.value, row.updated_by_id = value, user_id
    else:
        db.add(AppSetting(key=KEY, value=value, updated_by_id=user_id))
    db.flush()


def anthropic_key(db: Session) -> str:
    env = get_settings().anthropic_api_key
    if env:
        return env
    row = db.get(AppSetting, KEY)
    if not row or not row.value.get("enc"):
        return ""
    try:
        return _fernet().decrypt(row.value["enc"].encode()).decode()
    except InvalidToken:  # the server's secret changed: the key must be pasted again
        return ""


def anthropic_key_hint(db: Session) -> dict:
    if get_settings().anthropic_api_key:
        return {"set": True, "where": "server", "last4": get_settings().anthropic_api_key[-4:]}
    row = db.get(AppSetting, KEY)
    ok = bool(row and row.value.get("enc") and anthropic_key(db))
    return {"set": ok, "where": "settings" if ok else None, "last4": row.value.get("last4") if ok else None}


# ---- generic secrets (Shopify etc.), same encryption, never sent to the browser ----
def set_secret(db: Session, name: str, value: str | None, user_id: int | None, extra: dict | None = None) -> None:
    key = "secret." + name
    row = db.get(AppSetting, key)
    v = {"enc": _fernet().encrypt(value.encode()).decode(), "last4": value[-4:], **(extra or {})} if value else {}
    if row:
        row.value, row.updated_by_id = v, user_id
    else:
        db.add(AppSetting(key=key, value=v, updated_by_id=user_id))
    db.flush()


def get_secret(db: Session, name: str) -> str:
    row = db.get(AppSetting, "secret." + name)
    if not row or not row.value.get("enc"):
        return ""
    try:
        return _fernet().decrypt(row.value["enc"].encode()).decode()
    except InvalidToken:
        return ""


def secret_meta(db: Session, name: str) -> dict:
    row = db.get(AppSetting, "secret." + name)
    return dict(row.value) if row and row.value else {}


def secret_hint(db: Session, name: str) -> dict:
    ok = bool(get_secret(db, name))
    row = db.get(AppSetting, "secret." + name)
    return {"set": ok, "last4": row.value.get("last4") if ok and row else None}
