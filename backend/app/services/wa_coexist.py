"""Connect the CURRENT WhatsApp Business app number to the inbox (Meta "Coexistence"), Hayah 2026-11-19.

HAYAH is a Meta Tech Provider, so the onboarding runs through Embedded Signup with
featureType "whatsapp_business_app_onboarding" (sessionInfoVersion 3). The super admin presses
the button in Settings → WhatsApp, logs in to Facebook and scans the QR code shown in the
WhatsApp Business app on the phone. The browser then sends us a one-time `code` plus the
phone_number_id and waba_id, and the server:

1. exchanges the code for a business token (stored encrypted, never sent back);
2. subscribes the app to the WhatsApp Business Account's webhooks;
3. saves the phone number id / WABA id as the inbox number;
4. asks Meta to sync contacts (smb_app_state_sync) and then the chat history (history), which must
   happen within 24 hours of onboarding. Both can be retried from Settings.

Coexistence numbers are NOT registered with /register (that would take the number away from the
phone app). Nothing is sent to customers by any of these steps.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, utcnow
from app.services import secrets_store
from app.services import wa_inbox as wa
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

KEY = "whatsapp_coexistence"


def _graph() -> str:
    return f"https://graph.facebook.com/{get_settings().whatsapp_graph_version}"


def state(db: Session) -> dict:
    s = get_setting(db, KEY) or {}
    sync_deadline = None
    if s.get("onboarded_at"):
        sync_deadline = (datetime.fromisoformat(s["onboarded_at"]) + timedelta(hours=24)).isoformat()
    return {"app_id": s.get("app_id"), "config_id": s.get("config_id"), "graph_version": get_settings().whatsapp_graph_version,
            "onboarded_at": s.get("onboarded_at"), "phone_number_id": s.get("phone_number_id"), "waba_id": s.get("waba_id"),
            "contacts_sync_at": s.get("contacts_sync_at"), "history_sync_at": s.get("history_sync_at"),
            "history_progress": s.get("history_progress"), "sync_deadline": sync_deadline, "last_error": s.get("last_error"),
            "app_secret_set": bool(wa.app_secret(db)), "mock": wa.mock()}


def save_ids(db: Session, app_id: str, config_id: str, user: User) -> dict:
    s = get_setting(db, KEY) or {}
    s["app_id"], s["config_id"] = app_id.strip(), config_id.strip()
    set_setting(db, KEY, s, user.id)
    audit(db, "whatsapp.coexistence.ids", "settings", KEY, actor=user, after={"app_id": s["app_id"], "config_id": s["config_id"]})
    db.commit()
    return state(db)


def _call(method: str, path: str, token: str | None = None, **kw) -> dict:
    """One Graph API call. Isolated so tests replace it."""
    if wa.mock():
        if path.endswith("/oauth/access_token"):
            return {"access_token": "mock-business-token"}
        return {"success": True}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.request(method, _graph() + path, headers=headers, timeout=30.0, **kw)
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Meta. Try again.")
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        msg = (data.get("error") or {}).get("message") or f"Meta answered {r.status_code}"
        raise HTTPException(502, f"Meta: {msg}")
    return data


def finish_signup(db: Session, code: str, phone_number_id: str, waba_id: str, user: User) -> dict:
    s = get_setting(db, KEY) or {}
    if not s.get("app_id"):
        raise HTTPException(409, "Add the Meta app ID and the Embedded Signup configuration ID first.")
    secret = wa.app_secret(db)
    if not secret and not wa.mock():
        raise HTTPException(409, "Add the Meta app secret first (WhatsApp settings above).")
    tok = _call("GET", "/oauth/access_token", params={"client_id": s["app_id"], "client_secret": secret, "code": code})
    token = tok.get("access_token")
    if not token:
        raise HTTPException(502, "Meta did not return a token. Try the button again.")
    _call("POST", f"/{waba_id}/subscribed_apps", token)
    before = wa.config(db)
    wa.save_config(db, phone_number_id=phone_number_id, waba_id=waba_id,
                   display_number=before.get("display_number"), user=user, access_token_value=token)
    s.update({"onboarded_at": utcnow().isoformat(), "phone_number_id": phone_number_id, "waba_id": waba_id,
              "contacts_sync_at": None, "history_sync_at": None, "last_error": None})
    set_setting(db, KEY, s, user.id)
    audit(db, "whatsapp.coexistence.onboarded", "settings", KEY, actor=user, after={"phone_number_id": phone_number_id, "waba_id": waba_id})
    db.commit()
    return start_sync(db, user)


def start_sync(db: Session, user: User | None) -> dict:
    """Contacts first, then history (Meta's order). Safe to press again; each step is done once."""
    s = get_setting(db, KEY) or {}
    pid = s.get("phone_number_id")
    if not pid:
        raise HTTPException(409, "Connect the number first.")
    if s.get("onboarded_at") and utcnow() - datetime.fromisoformat(s["onboarded_at"]) > timedelta(hours=24) \
            and not (s.get("contacts_sync_at") and s.get("history_sync_at")):
        raise HTTPException(409, "More than 24 hours passed since connecting, so Meta no longer allows the sync. Connect again to sync.")
    token = wa.access_token(db)
    try:
        for step, field in (("smb_app_state_sync", "contacts_sync_at"), ("history", "history_sync_at")):
            if not s.get(field):
                _call("POST", f"/{pid}/smb_app_data", token, json={"messaging_product": "whatsapp", "sync_type": step})
                s[field] = utcnow().isoformat()
        s["last_error"] = None
    except HTTPException as e:
        s["last_error"] = e.detail
    set_setting(db, KEY, s, user.id if user else None)
    audit(db, "whatsapp.coexistence.sync", "settings", KEY, actor=user, after={k: s.get(k) for k in ("contacts_sync_at", "history_sync_at", "last_error")})
    db.commit()
    return state(db)


# ---------------- webhooks: history and contacts ----------------
def handle_history(db: Session, value: dict, business_wa_id: str | None) -> set[str]:
    """`history` webhook: past chats from the phone app (up to 6 months). Stored once each."""
    taken, s = set(), get_setting(db, KEY) or {}
    for chunk in value.get("history") or []:
        meta = chunk.get("metadata") or {}
        if meta.get("progress") is not None:
            s["history_progress"] = meta.get("progress")
        for th in chunk.get("threads") or []:
            customer = th.get("id")
            if not customer:
                continue
            conv = wa.get_or_create(db, customer)
            for m in th.get("messages") or []:
                if not m.get("id"):
                    continue
                frm = wa._digits(m.get("from"))
                direction = "in" if frm and frm == wa._digits(customer) and frm != wa._digits(business_wa_id) else "out"
                wa._store(db, conv, m, direction, "history")
                taken.add(m["id"])
    set_setting(db, KEY, s)
    return taken


def handle_contacts(db: Session, value: dict) -> None:
    """`smb_app_state_sync` webhook: contacts saved in the phone app give chats their names."""
    for item in value.get("state_sync") or []:
        c = item.get("contact") or {}
        if item.get("type") != "contact" or item.get("action") == "remove" or not c.get("phone_number"):
            continue
        conv = wa.get_or_create(db, c["phone_number"])
        name = c.get("full_name") or c.get("first_name")
        if name:
            conv.contact_name = name[:200]
