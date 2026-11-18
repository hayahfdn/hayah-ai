import pytest

from app.models import AuditLog, UsageRecord


@pytest.fixture
def fake_claude(monkeypatch):
    """Replace the network call; everything after it (validation, preview, apply) is real."""
    from app.config import get_settings
    from app.services import assistant
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "test-key")
    plans = {}

    def fake(db, prompt, page):
        return plans["next"], {"model": "test", "input_tokens": 1000, "output_tokens": 200}
    monkeypatch.setattr(assistant, "_call_model", fake)
    return plans


def enable_ai(client, admin):
    r = client.put("/api/settings/ai", headers=admin, json={"ai_enabled": True, "monthly_budget_usd": 100,
                                                             "min_confidence": 0.9, "manual_approval_over_usd": 0.25})
    assert r.status_code == 200


def ops(*items):
    return [{"op": o, "target": t, "fields": [{"name": k, "value": v} for k, v in f.items()]} for o, t, f in items]


def test_without_key_explains_what_is_missing(client, manager):
    r = client.post("/api/assistant/plan", headers=manager, json={"prompt": "mark 9003 completed"})
    assert r.status_code == 503 and "Anthropic" in r.json()["detail"]
    assert client.get("/api/assistant/status", headers=manager).json()["ready"] is False


def test_plan_previews_and_apply_writes_through_audited_path(client, admin, manager, db, fake_claude):
    enable_ai(client, admin)
    prompt = "Well 9003 is finished, cost 1100, contractor PAK2. Add Facebook ads 40 from Wise today."
    fake_claude["next"] = {"summary": "ok", "questions": [], "operations": ops(
        ("update_well", "9003", {"construction_status": "completed", "cost": "1100", "contractor_id": "PAK2"}),
        ("add_transaction", "", {"date": "2026-11-18", "kind": "ad_spend", "channel": "Facebook", "amount": "40", "account_id": "WISE"}),
    )}
    plan = client.post("/api/assistant/plan", headers=manager, json={"prompt": prompt}).json()
    assert plan["can_apply"], plan
    before = client.get("/api/projects/9003", headers=manager).json()
    assert before["construction_status"] == "in_progress"  # planning wrote nothing
    ch = {c["field"]: c for c in plan["operations"][0]["changes"]}
    assert ch["construction_status"]["from"] == "in_progress" and ch["construction_status"]["to"] == "completed"
    assert db.query(UsageRecord).filter_by(service="anthropic").count() == 1

    r = client.post("/api/assistant/apply", headers=manager, json={"prompt": prompt, "operations": plan["operations"]})
    assert r.status_code == 200 and r.json()["applied"] == 2
    after = client.get("/api/projects/9003", headers=manager).json()
    assert after["construction_status"] == "completed" and after["cost"] == "1100.00"
    assert after["delivery_status"] == "pending"  # completion is never delivery
    assert db.query(AuditLog).filter(AuditLog.action == "assistant.apply").count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "project.update", AuditLog.entity_id == "9003").count() >= 1


def test_never_invents_ids_or_touches_delivery(client, admin, manager, fake_claude):
    enable_ai(client, admin)
    fake_claude["next"] = {"summary": "", "questions": [], "operations": ops(
        ("create_well", "1400", {"country": "Pakistan"}),             # number not in the prompt
        ("update_well", "9002", {"delivery_status": "delivered"}),    # delivery is off-limits
        ("update_well", "424242", {"notes": "x"}),                    # unknown well
        ("update_well", "9001", {"password": "x"}),                   # unknown field
    )}
    plan = client.post("/api/assistant/plan", headers=manager, json={"prompt": "add a new well in Pakistan"}).json()
    errs = [o["error"] for o in plan["operations"]]
    assert all(errs) and not plan["can_apply"]
    assert "not written" in errs[0] and "Delivery" in errs[1]
    r = client.post("/api/assistant/apply", headers=manager, json={"prompt": "add a new well in Pakistan", "operations": plan["operations"]})
    assert r.status_code == 422
    assert client.get("/api/projects/1400", headers=manager).status_code == 404


def test_new_number_written_in_prompt_is_allowed_arabic_digits(client, admin, manager, fake_claude):
    enable_ai(client, admin)
    prompt = "أضف أضحية رقم ٣٠٩٠ خروف التكلفة ١٢٠"
    fake_claude["next"] = {"summary": "", "questions": [], "operations": ops(
        ("create_sacrifice", "3090", {"animal_type": "خروف", "cost": "120", "contractor_id": "TZ1"}))}
    plan = client.post("/api/assistant/plan", headers=manager, json={"prompt": prompt}).json()
    assert plan["can_apply"], plan
    assert client.post("/api/assistant/apply", headers=manager, json={"prompt": prompt, "operations": plan["operations"]}).status_code == 200
    assert client.patch("/api/sacrifices/3090", headers=manager, json={}).json()["cost"] == "120.00"


def test_apply_is_all_or_nothing_and_rejects_stale_preview(client, admin, manager, fake_claude):
    enable_ai(client, admin)
    fake_claude["next"] = {"summary": "", "questions": [], "operations": ops(("update_well", "9004", {"notes": "via prompt"}))}
    plan = client.post("/api/assistant/plan", headers=manager, json={"prompt": "note on 9004"}).json()
    p = client.get("/api/projects/9004", headers=manager).json()
    client.patch("/api/projects/9004", headers=manager, json={"city": "Changed meanwhile", "expected_version": p["version"]})
    r = client.post("/api/assistant/apply", headers=manager, json={"prompt": "note on 9004", "operations": plan["operations"]})
    assert r.status_code == 409
    assert client.get("/api/projects/9004", headers=manager).json()["notes"] != "via prompt"


def test_budget_guard(client, admin, manager, db, fake_claude):
    from decimal import Decimal
    enable_ai(client, admin)
    db.add(UsageRecord(service="anthropic", operation="x", est_cost_usd=Decimal("100.5")))
    db.commit()
    r = client.post("/api/assistant/plan", headers=manager, json={"prompt": "anything"})
    assert r.status_code == 503 and "budget" in r.json()["detail"]


def test_viewer_and_contractor_cannot_use_prompt(client, seeded):
    from tests.conftest import login
    for email in ("viewer@hayah.local", "p1@hayah.local"):
        h = login(client, email)
        assert client.post("/api/assistant/plan", headers=h, json={"prompt": "x" * 5}).status_code == 403
