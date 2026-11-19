"""Floating help assistant: read only, grounded in the guide, respects roles and the AI budget."""
from types import SimpleNamespace as NS

import pytest

from app.models import Role, UsageRecord
from tests.conftest import login
from tests.test_assistant import enable_ai


def _resp(content, stop="end_turn"):
    return NS(content=content, stop_reason=stop, model="test",
              usage=NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0))


def _text(t):
    return NS(type="text", text=t, model_dump=lambda **_: {"type": "text", "text": t})


def _tool(name, number):
    return NS(type="tool_use", id="tu1", name=name, input={"number": number},
              model_dump=lambda **_: {"type": "tool_use", "id": "tu1", "name": name, "input": {"number": number}})


@pytest.fixture
def fake(monkeypatch):
    from app.config import get_settings
    from app.services import help_chat
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    calls, queue = [], []

    def create(db, **kw):
        calls.append(kw)
        return queue.pop(0)
    monkeypatch.setattr(help_chat, "_create", create)
    return NS(calls=calls, queue=queue)


def staff(client):
    return login(client, "staff@hayah.local")


def test_not_ready_without_key_in_plain_words(client, seeded):
    h = staff(client)
    st = client.get("/api/help/status", headers=h).json()
    assert st["ready"] is False and "Settings" in st["reason"]
    r = client.post("/api/help/ask", headers=h, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_staff_guide_has_no_money_sections():
    from app.services.help_chat import guide_for
    staff_guide, mgr_guide = guide_for(Role.staff), guide_for(Role.operations_manager)
    assert "## [managers]" not in staff_guide and "Cost and profit" not in staff_guide and "## [managers] Money" in mgr_guide
    assert "open icon" in staff_guide


def test_answer_and_usage_counted_in_shared_budget(client, admin, db, fake):
    enable_ai(client, admin)
    h = staff(client)
    fake.queue.append(_resp([_text("افتح «طلبات تحتاج تأكيد اللوحة» من القائمة.")]))
    r = client.post("/api/help/ask", headers=h, json={"messages": [{"role": "user", "content": "وين ألاقي اللوحات؟"}],
                                                      "page": "/projects"})
    assert r.status_code == 200, r.text
    assert "اللوحة" in r.json()["answer"]
    sent = fake.calls[0]
    assert "Never discuss cost" in sent["system"][0]["text"]
    assert [t["name"] for t in sent["tools"]] == ["lookup_well"]  # no sacrifices tool for staff
    assert "/projects" in sent["messages"][-1]["content"]
    assert db.query(UsageRecord).filter_by(operation="help_chat").count() == 1


def test_well_lookup_hides_cost_and_phone_from_staff(client, admin, fake):
    enable_ai(client, admin)
    fake.queue += [_resp([_tool("lookup_well", 9001)], stop="tool_use"), _resp([_text("Well 9001 is completed.")])]
    r = client.post("/api/help/ask", headers=staff(client), json={"messages": [{"role": "user", "content": "status of 9001?"}]})
    assert r.status_code == 200 and r.json()["looked_up"][0]["found"] is True
    result = fake.calls[1]["messages"][-1]["content"][0]["content"]
    assert '"well_id": 9001' in result and "cost_usd" not in result and "phone" not in result


def test_manager_lookup_includes_cost_and_sacrifices(client, admin, db, fake):
    from app.services.help_chat import lookup_sacrifice, lookup_well
    from app.models import User
    enable_ai(client, admin)
    mgr = db.query(User).filter_by(email="manager@hayah.local").one()
    st = db.query(User).filter_by(email="staff@hayah.local").one()
    assert "cost_usd" in lookup_well(db, mgr, 9001)
    assert lookup_sacrifice(db, st, 90001) == {"error": "Sacrifices are for managers only."}


def test_contractor_sees_only_own_wells(db, seeded):
    from app.models import Project, User
    from app.services.help_chat import lookup_well
    c = db.query(User).filter_by(email="p1@hayah.local").one()
    own = db.query(Project).filter(Project.contractor_id == c.contractor_id).first()
    other = db.query(Project).filter(Project.contractor_id != c.contractor_id).first()
    assert lookup_well(db, c, own.well_id)["found"] is True
    assert lookup_well(db, c, other.well_id) == {"found": False, "number": other.well_id}
    assert "selling_price_usd" not in lookup_well(db, c, own.well_id)
