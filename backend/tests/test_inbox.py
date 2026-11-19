"""WhatsApp inbox on the Cloud API (mock client): signed webhooks, chats linked to orders by phone,
media download, sending with the 24-hour window and templates, no duplicate sends, statuses,
echoes from the phone app (Coexistence), assignment, counts and access rules."""
import hashlib
import hmac
import io
import json
import time
import uuid

from app.integrations.whatsapp import MockWhatsAppClient, WaSendError
from app.services.jobs import run_due_jobs
from tests.conftest import login
from tests.test_ui_upgrade import _tiny_png

SECRET = b"app-secret"
INBOX = "555000111"
CUSTOMER = "962791234567"


def _post(client, payload):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def _value(field="messages", **v):
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": field, "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": INBOX}, **v}}]}]}


def _incoming(mid, text=None, frm=CUSTOMER, name="أبو خالد", image=None, ts=None):
    m = {"from": frm, "id": mid, "timestamp": str(ts or int(time.time())), "type": "text"}
    if image:
        m.update(type="image", image={"id": image, "mime_type": "image/png", "caption": text})
    else:
        m["text"] = {"body": text}
    return _value(contacts=[{"wa_id": frm, "profile": {"name": name}}], messages=[m])


def _connect(client):
    admin = login(client, "admin@hayah.local")
    r = client.put("/api/settings/whatsapp-inbox", headers=admin, json={"phone_number_id": INBOX, "waba_id": "777", "display_number": "+962 6 000"})
    assert r.status_code == 200 and r.json()["enabled"], r.text
    return admin


def _send(client, h, cid, **body):
    return client.post(f"/api/inbox/conversations/{cid}/send", headers=h, json={"client_ref": uuid.uuid4().hex, **body})


def test_receive_link_reply_and_statuses(client, seeded, mocks, db):
    _connect(client)
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/projects", headers=staff, json={"well_id": 7301, "well_type": "يدوي", "country": "Pakistan",
                                                           "customer_name": "أبو خالد", "customer_phone": "+962 79 123 4567"})
    assert r.status_code == 201
    # a bad signature is refused
    body = json.dumps(_incoming("wamid.x0", "hi")).encode()
    assert client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=00", "Content-Type": "application/json"}).status_code == 401
    assert _post(client, _incoming("wamid.in1", "السلام عليكم، متى يجهز البئر؟")).status_code == 200
    assert _post(client, _incoming("wamid.in1", "السلام عليكم، متى يجهز البئر؟")).status_code == 200  # Meta re-sends: stored once
    convs = client.get("/api/inbox/conversations", headers=staff).json()
    assert len(convs) == 1
    c = convs[0]
    assert c["phone"] == "+" + CUSTOMER and c["name"] == "أبو خالد" and c["unread"] == 1 and c["waiting_reply"] and c["window_open"]
    assert c["order"]["kind"] == "well" and c["order"]["number"] == 7301  # linked automatically by phone
    assert c["plaque_unconfirmed"]  # the order's plaque is still a draft
    # the intake pipeline did not take the customer's message
    from app.models import InboundMessage
    assert db.query(InboundMessage).count() == 0
    counts = client.get("/api/ops/counts", headers=staff).json()["whatsapp"]
    assert counts["unread_messages"] == 1 and counts["waiting_reply"] == 1 and counts["enabled"]
    # reply; the same client_ref twice sends once
    ref = uuid.uuid4().hex
    MockWhatsAppClient.sent.clear()
    m1 = client.post(f"/api/inbox/conversations/{c['id']}/send", headers=staff, json={"client_ref": ref, "text": "وعليكم السلام"}).json()
    m2 = client.post(f"/api/inbox/conversations/{c['id']}/send", headers=staff, json={"client_ref": ref, "text": "وعليكم السلام"}).json()
    assert m1["id"] == m2["id"] and m1["status"] == "sent" and m1["sent_by"] and len(MockWhatsAppClient.sent) == 1
    assert MockWhatsAppClient.sent[0]["to"] == CUSTOMER and MockWhatsAppClient.sent[0]["text"]["body"] == "وعليكم السلام"
    wid = MockWhatsAppClient.sent[0]["id"]
    # statuses move forward only
    st = lambda s: _value(statuses=[{"id": wid, "status": s, "timestamp": str(int(time.time())), "recipient_id": CUSTOMER}])  # noqa: E731
    _post(client, st("read"))
    _post(client, st("delivered"))
    msgs = client.get(f"/api/inbox/conversations/{c['id']}/messages", headers=staff).json()
    assert [m["direction"] for m in msgs] == ["in", "out"] and msgs[1]["status"] == "read"
    # mark read, then the chat no longer waits for a reply
    client.post(f"/api/inbox/conversations/{c['id']}/read", headers=staff)
    c = client.get(f"/api/inbox/conversations/{c['id']}", headers=staff).json()
    assert c["unread"] == 0 and not c["waiting_reply"] and c["orders"][0]["linked"]


def test_window_templates_failures_and_retry(client, seeded, mocks):
    _connect(client)
    staff = login(client, "staff@hayah.local")
    old = int(time.time()) - 26 * 3600
    _post(client, _incoming("wamid.old", "قديم", ts=old))
    cid = client.get("/api/inbox/conversations", headers=staff).json()[0]["id"]
    # more than 24 hours: free text refused, an approved template is allowed
    r = _send(client, staff, cid, text="مرحبا")
    assert r.status_code == 409 and "24" in r.json()["detail"]
    tpls = client.get("/api/inbox/templates", headers=staff).json()
    assert {t["name"] for t in tpls} >= {"order_update"} and next(t for t in tpls if t["name"] == "order_update")["params"] == 2
    MockWhatsAppClient.sent.clear()
    r = _send(client, staff, cid, template={"name": "order_update", "language": "ar", "params": ["أبو خالد", "7301"]})
    assert r.status_code == 201 and r.json()["status"] == "sent"
    sent = MockWhatsAppClient.sent[-1]["template"]
    assert sent["name"] == "order_update" and sent["components"][0]["parameters"][1]["text"] == "7301"
    # inside the window: a refusal from Meta fails the message; a network error retries in the background
    _post(client, _incoming("wamid.new", "جديد"))
    MockWhatsAppClient.fail_next.append(WaSendError("WhatsApp: bad number (code 131026)", transient=False))
    r = _send(client, staff, cid, text="test").json()
    assert r["status"] == "failed" and "131026" in r["error"]
    retried = client.post(f"/api/inbox/messages/{r['id']}/retry", headers=staff).json()
    assert retried["status"] == "sent" and retried["id"] == r["id"]
    MockWhatsAppClient.fail_next.append(WaSendError("WhatsApp could not be reached", transient=True))
    q = _send(client, staff, cid, text="later").json()
    assert q["status"] == "queued"
    from app.db import SessionLocal
    from app.models import Job
    s = SessionLocal()
    try:
        s.query(Job).update({"next_run_at": Job.created_at})
        s.commit()
        run_due_jobs(s)
    finally:
        s.close()
    msgs = client.get(f"/api/inbox/conversations/{cid}/messages", headers=staff).json()
    assert next(m for m in msgs if m["id"] == q["id"])["status"] == "sent"


def test_media_in_and_out_and_order_files(client, seeded, mocks):
    _connect(client)
    staff = login(client, "staff@hayah.local")
    MockWhatsAppClient.media["media-1"] = (_tiny_png(321), "image/png")
    _post(client, _incoming("wamid.img", "صورة الحوالة", image="media-1"))
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        run_due_jobs(s)
    finally:
        s.close()
    cid = client.get("/api/inbox/conversations", headers=staff).json()[0]["id"]
    m = client.get(f"/api/inbox/conversations/{cid}/messages", headers=staff).json()[0]
    assert m["type"] == "image" and m["file"] and m["text"] == "صورة الحوالة"
    f = client.get(m["file"])
    assert f.status_code == 200 and f.content.startswith(b"\x89PNG")
    assert client.get(m["file"].split("?")[0] + "?t=bad").status_code == 401
    # send a PDF from the computer
    MockWhatsAppClient.sent.clear()
    r = client.post(f"/api/inbox/conversations/{cid}/upload", headers=staff,
                    data={"client_ref": uuid.uuid4().hex, "caption": "الإيصال"},
                    files={"file": ("receipt.pdf", io.BytesIO(b"%PDF-1.4\n%test\n"), "application/pdf")})
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "document" and MockWhatsAppClient.sent[-1]["document"]["filename"] == "receipt.pdf"
    # a program is refused
    r = client.post(f"/api/inbox/conversations/{cid}/upload", headers=staff, data={"client_ref": uuid.uuid4().hex},
                    files={"file": ("x.pdf", io.BytesIO(b"MZ\x90\x00 program"), "application/pdf")})
    assert r.status_code == 415
    # the linked order's final video can be sent; that records it on the order and marks the video sent
    client.post("/api/projects", headers=staff, json={"well_id": 7302, "well_type": "يدوي", "country": "Pakistan"})
    client.post(f"/api/inbox/conversations/{cid}/link", headers=staff, json={"kind": "well", "number": 7302})
    from tests.test_final_video import _mp4, _up
    _up(client, staff, "well", 7302, _mp4(77))
    att = client.get(f"/api/inbox/conversations/{cid}/attachables", headers=staff).json()
    vid = next(a for a in att if a["kind"] == "final_video")
    r = _send(client, staff, cid, asset_id=vid["asset_id"], text="الفيديو النهائي لبئركم")
    assert r.status_code == 201 and r.json()["type"] == "video" and MockWhatsAppClient.sent[-1]["video"]["caption"]
    assert client.get("/api/videos/order/well/7302", headers=staff).json()["status"] == "sent_to_customer"
    events = [e["event_type"] for e in client.get("/api/projects/7302/history", headers=staff).json()["events"]]
    assert "whatsapp_sent" in events and "whatsapp_linked" in events


def test_phone_app_echoes_assignment_and_access(client, seeded, mocks):
    _connect(client)
    staff, mgr = login(client, "staff@hayah.local"), login(client, "manager@hayah.local")
    _post(client, _incoming("wamid.a", "مرحبا"))
    # a reply typed on the phone in the WhatsApp Business app shows in the same chat
    echo = _value("smb_message_echoes", message_echoes=[{"from": "9626000", "to": CUSTOMER, "id": "wamid.echo1",
                                                          "timestamp": str(int(time.time())), "type": "text", "text": {"body": "أهلاً"}}])
    assert _post(client, echo).status_code == 200
    cid = client.get("/api/inbox/conversations", headers=staff).json()[0]["id"]
    msgs = client.get(f"/api/inbox/conversations/{cid}/messages", headers=staff).json()
    assert msgs[-1]["direction"] == "out" and msgs[-1]["source"] == "phone_app"
    me = client.get("/api/auth/me", headers=staff).json()["id"]
    boss = client.get("/api/auth/me", headers=mgr).json()["id"]
    assert client.post(f"/api/inbox/conversations/{cid}/assign", headers=staff, json={"user_id": me}).json()["assigned_to_id"] == me
    assert [c["id"] for c in client.get("/api/inbox/conversations?box=mine", headers=staff).json()] == [cid]
    # the manager moves it; the employee then cannot take it back
    assert client.post(f"/api/inbox/conversations/{cid}/assign", headers=mgr, json={"user_id": boss}).status_code == 200
    assert client.post(f"/api/inbox/conversations/{cid}/assign", headers=staff, json={"user_id": me}).status_code == 403
    assert client.post(f"/api/inbox/conversations/{cid}/status", headers=staff, json={"status": "closed"}).json()["status"] == "closed"
    _post(client, _incoming("wamid.b", "سؤال آخر"))  # the customer writes again: reopened
    assert client.get(f"/api/inbox/conversations/{cid}", headers=staff).json()["status"] == "open"
    for who in ("p1@hayah.local", "viewer@hayah.local", "maint@hayah.local"):
        h = login(client, who)
        assert client.get("/api/inbox/conversations", headers=h).status_code == 403
        assert _send(client, h, cid, text="x").status_code == 403
    assert client.get("/api/settings/whatsapp-inbox", headers=staff).status_code == 403
    # secrets never come back
    st = client.get("/api/settings/whatsapp-inbox", headers=login(client, "admin@hayah.local")).json()
    assert "app-secret" not in json.dumps(st)


def test_not_connected_and_intake_number_unchanged(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    # without inbox settings, messages keep going to the intake pipeline as before
    assert _post(client, _incoming("wamid.i1", "#B 1339 تم التسليم", frm="920000000002")).status_code == 200
    assert client.get("/api/inbox/conversations", headers=staff).json() == []
    assert client.get("/api/ops/counts", headers=staff).json()["whatsapp"]["enabled"] is False
