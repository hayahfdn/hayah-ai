import hashlib
import hmac
import json
import time

from app.cli import _tiny_png
from app.integrations.ai.rules import extract
from app.integrations.whatsapp import MockWhatsAppClient
from app.models import InboundMessage, ReviewCase
from app.services.jobs import run_due_jobs

SECRET = b"app-secret"


def wa_payload(msg_id, text=None, sender="920000000002", image_id=None, caption=None):
    m = {"from": sender, "id": msg_id, "timestamp": str(int(time.time())), "type": "text"}
    if image_id:
        m.update(type="image", image={"id": image_id, "mime_type": "image/png", "caption": caption})
    else:
        m["text"] = {"body": text}
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "123"},
        "contacts": [{"wa_id": sender, "profile": {"name": "Field Team"}}], "messages": [m]}}]}]}


def post_wa(client, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig,
                                                                   "Content-Type": "application/json"})


# ---------- extraction (rules engine, no AI cost) ----------
def test_rules_arabic_delivery():
    ex = extract("1339 تم التسليم للعائلة اليوم الحمد لله", "B")
    assert ex.well_id == 1339 and ex.event_type == "delivery_confirmation" and ex.language == "ar"
    assert not ex.requires_human_review


def test_rules_english_construction_and_arabic_digits():
    ex = extract("Well 1340 drilling completed, pump installed", "A")
    assert ex.well_id == 1340 and ex.event_type == "construction_update"
    assert ex.construction.construction_status == "completed"
    assert extract("البئر ١٣٤١ اكتمل", "A").well_id == 1341


def test_rules_never_guess_well_id():
    ex = extract("الحمد لله تم الانتهاء من البئر", "A")
    assert ex.well_id is None and ex.requires_human_review and "well_id" in ex.missing_fields
    ex = extract("1339 and 1340 completed", "A")
    assert ex.well_id is None and ex.requires_human_review
    assert extract("call +923001234567 on 17/11/2026", None).well_ids == []


# ---------- webhook ----------
def test_webhook_verification(client):
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                 "hub.challenge": "abc"})
    assert r.status_code == 200 and r.text == "abc"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x",
                                                    "hub.challenge": "abc"}).status_code == 403


def test_webhook_rejects_bad_signature(client):
    assert post_wa(client, wa_payload("wamid.1", "hi"), secret=b"wrong").status_code == 401


def test_construction_update_from_registered_contractor(client, manager, db):
    assert post_wa(client, wa_payload("wamid.A1", "#A 9002 completed, handle fitted")).json()["received"] == 1
    run_due_jobs(db)
    # 9002 was already completed; use 9010 in progress → check event recorded
    post_wa(client, wa_payload("wamid.A2", "#A 9010 اكتمل الحفر"))
    run_due_jobs(db)
    msg = db.query(InboundMessage).filter_by(external_id="wamid.A2").one()
    assert msg.processing_status == "applied" and msg.group_label == "A"
    events = client.get("/api/projects/9010/history", headers=manager).json()["events"]
    assert any(e["event_type"] == "whatsapp_message" for e in events)


def test_duplicate_webhook_delivery_is_idempotent(client, manager, db):
    for _ in range(3):
        post_wa(client, wa_payload("wamid.DUP", "#D 9001 الطلمبة معطلة"))
    run_due_jobs(db)
    assert db.query(InboundMessage).filter_by(external_id="wamid.DUP").count() == 1
    recs = client.get("/api/maintenance", params={"well_id": 9001}, headers=manager).json()
    assert len(recs) == 2  # seeded one + exactly one new


def test_group_b_delivery_creates_pending_only(client, manager, db):
    post_wa(client, wa_payload("wamid.B1", "#B 9010 تم التسليم للعائلة"))
    run_due_jobs(db)
    assert client.get("/api/projects/9010", headers=manager).json()["delivery_status"] == "pending"
    pending = client.get("/api/delivery", params={"status": "pending"}, headers=manager).json()
    dc = next(d for d in pending if d["well_id"] == 9010 and d["source"] == "whatsapp")
    client.post(f"/api/delivery/{dc['id']}/decision", json={"approve": True}, headers=manager)
    assert client.get("/api/projects/9010", headers=manager).json()["delivery_status"] == "delivered"


def test_unknown_well_and_missing_well_go_to_review(client, manager, db):
    post_wa(client, wa_payload("wamid.U1", "#A 7777 completed"))
    post_wa(client, wa_payload("wamid.U2", "#A تم الانتهاء من البئر الحمد لله"))
    run_due_jobs(db)
    cases = client.get("/api/review", headers=manager).json()
    texts = {c["message_text"] for c in cases}
    assert "#A 7777 completed" in texts and "#A تم الانتهاء من البئر الحمد لله" in texts
    # reviewer assigns the right well → applied
    case = next(c for c in cases if c["message_text"].startswith("#A تم"))
    r = client.post(f"/api/review/{case['id']}/decision", json={"approve": True, "well_id": 9005}, headers=manager)
    assert r.status_code == 200
    assert client.get("/api/projects/9005", headers=manager).json()["construction_status"] == "completed"


def test_unregistered_sender_cannot_change_data(client, manager, db):
    post_wa(client, wa_payload("wamid.X1", "#A 9004 completed", sender="15550000000"))
    run_due_jobs(db)
    assert client.get("/api/projects/9004", headers=manager).json()["construction_status"] == "new_order"
    assert db.query(ReviewCase).count() >= 1


def test_image_message_saved_to_drive(client, manager, db, mocks):
    MockWhatsAppClient.media["media-1"] = (_tiny_png(5), "image/png")
    post_wa(client, wa_payload("wamid.IMG", image_id="media-1", caption="#A 9003 started drilling"))
    run_due_jobs(db)
    media = client.get("/api/media", params={"well_id": 9003}, headers=manager).json()
    assert len(media) == 2 and any(m["source"] == "whatsapp" for m in media)


def test_manual_paste_fallback(client, manager):
    r = client.post("/api/intake/manual", json={"text": "9008 new well started drilling", "group_label": "A"},
                    headers=manager)
    assert r.status_code == 200 and r.json()["status"] == "applied"
    assert client.get("/api/projects/9008", headers=manager).json()["construction_status"] == "in_progress"
