"""Coexistence onboarding: code exchange, webhook subscription, contacts then history sync (once),
history and contact webhooks stored once, no /register call, admins only."""
import time

from app.models import WaConversation, WaMessage
from app.services import wa_coexist
from tests.conftest import login
from tests.test_inbox import CUSTOMER, INBOX, _post, _value


def _setup(client, monkeypatch):
    calls = []

    def fake(method, path, token=None, **kw):
        calls.append((method, path, kw.get("json")))
        return {"access_token": "biz-token"} if path.endswith("/oauth/access_token") else {"success": True}
    monkeypatch.setattr(wa_coexist, "_call", fake)
    admin = login(client, "admin@hayah.local")
    assert client.put("/api/settings/whatsapp-coexistence", headers=admin, json={"app_id": "123456", "config_id": "987654"}).status_code == 200
    return admin, calls


def test_finish_signup_connects_and_syncs_once(client, seeded, mocks, monkeypatch):
    admin, calls = _setup(client, monkeypatch)
    r = client.post("/api/settings/whatsapp-coexistence/finish", headers=admin,
                    json={"code": "abc123code", "phone_number_id": INBOX, "waba_id": "777"})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["contacts_sync_at"] and st["history_sync_at"] and st["sync_deadline"]
    paths = [p for _, p, _ in calls]
    assert paths == ["/oauth/access_token", "/777/subscribed_apps", f"/{INBOX}/smb_app_data", f"/{INBOX}/smb_app_data"]
    assert [j["sync_type"] for _, p, j in calls if p.endswith("smb_app_data")] == ["smb_app_state_sync", "history"]
    assert not any("register" in p for p in paths)
    inbox = client.get("/api/settings/whatsapp-inbox", headers=admin).json()
    assert inbox["phone_number_id"] == INBOX and inbox["access_token"]["where"] == "settings"
    assert "biz-token" not in str(inbox)
    calls.clear()
    client.post("/api/settings/whatsapp-coexistence/sync", headers=admin)
    assert calls == []  # each sync step is asked for once


def test_history_and_contacts_webhooks(client, seeded, mocks, monkeypatch):
    admin, _ = _setup(client, monkeypatch)
    client.post("/api/settings/whatsapp-coexistence/finish", headers=admin, json={"code": "abc123code", "phone_number_id": INBOX, "waba_id": "777"})
    ts = str(int(time.time()) - 86400 * 30)
    hist = _value("history", history=[{"metadata": {"phase": 0, "chunk_order": 1, "progress": 100}, "threads": [{"id": CUSTOMER, "messages": [
        {"from": CUSTOMER, "id": "wamid.h1", "timestamp": ts, "type": "text", "text": {"body": "السلام عليكم"}},
        {"from": "9626000", "id": "wamid.h2", "timestamp": ts, "type": "text", "text": {"body": "وعليكم السلام"}}]}]}])
    for _ in range(2):  # Meta may send the same chunk again
        assert _post(client, hist).status_code == 200
    contacts = _value("smb_app_state_sync", state_sync=[{"type": "contact", "action": "add",
                                                         "contact": {"full_name": "Abu Khaled", "phone_number": CUSTOMER}}])
    assert _post(client, contacts).status_code == 200
    from app.db import SessionLocal
    db = SessionLocal()
    conv = db.query(WaConversation).filter_by(wa_id=CUSTOMER).one()
    msgs = {m.wa_message_id: m for m in db.query(WaMessage).filter_by(conversation_id=conv.id)}
    assert set(msgs) == {"wamid.h1", "wamid.h2"}
    assert msgs["wamid.h1"].direction == "in" and msgs["wamid.h2"].direction == "out"
    assert conv.contact_name == "Abu Khaled"
    assert client.get("/api/settings/whatsapp-coexistence", headers=admin).json()["history_progress"] == 100
    db.close()


def test_admin_only(client, seeded):
    for email in ("manager@hayah.local", "staff@hayah.local"):
        h = login(client, email)
        assert client.get("/api/settings/whatsapp-coexistence", headers=h).status_code == 403
