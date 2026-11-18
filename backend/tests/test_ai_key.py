from sqlalchemy import select

from app.models import AppSetting
from tests.test_assistant import enable_ai


def test_admin_pastes_key_it_is_encrypted_and_never_returned(client, admin, manager, db, monkeypatch):
    from app.services import assistant
    monkeypatch.setattr(assistant, "_call_model", lambda db, p, page: (
        {"summary": "Everything is already in US dollars ($).", "questions": [], "operations": []},
        {"model": "test", "input_tokens": 10, "output_tokens": 5}))
    key = "sk-ant-api03-TESTKEY-abcd1234"
    assert client.put("/api/settings/ai-key", headers=manager, json={"api_key": key}).status_code == 403
    assert client.put("/api/settings/ai-key", headers=admin, json={"api_key": "hello"}).status_code == 422
    r = client.put("/api/settings/ai-key", headers=admin, json={"api_key": key})
    assert r.status_code == 200 and r.json() == {"set": True, "where": "settings", "last4": "1234"}
    stored = db.scalar(select(AppSetting).where(AppSetting.key == "secret.anthropic_api_key"))
    assert key not in str(stored.value)
    assert key not in client.get("/api/settings", headers=admin).text
    enable_ai(client, admin)
    assert client.get("/api/assistant/status", headers=manager).json()["ready"] is True
    r = client.post("/api/assistant/plan", headers=manager, json={"prompt": "the currency is $"})
    assert r.status_code == 200, r.text
    assert r.json()["operations"] == [] and "$" in r.json()["summary"]
    client.put("/api/settings/ai-key", headers=admin, json={"api_key": ""})
    assert client.get("/api/assistant/status", headers=manager).json()["ready"] is False


