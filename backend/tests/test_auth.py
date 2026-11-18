from tests.conftest import login


def test_login_and_me(client, seeded):
    h = login(client, "admin@hayah.local")
    r = client.get("/api/auth/me", headers=h)
    assert r.json()["role"] == "super_admin"


def test_wrong_password_rejected_and_audited(client, seeded, db):
    r = client.post("/api/auth/login", json={"email": "admin@hayah.local", "password": "nope"})
    assert r.status_code == 401
    from app.models import AuditLog
    assert db.query(AuditLog).filter_by(action="auth.login_failed").count() == 1


def test_login_rate_limited(client, seeded):
    codes = [client.post("/api/auth/login", json={"email": "x@hayah.local", "password": "bad"}).status_code
             for _ in range(12)]
    assert 429 in codes


def test_requires_token(client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_permissions(client, seeded):
    viewer = login(client, "viewer@hayah.local")
    assert client.get("/api/projects", headers=viewer).status_code == 200
    assert client.patch("/api/projects/9003", json={"notes": "x"}, headers=viewer).status_code == 403
    assert client.post("/api/projects", json={"well_id": 5}, headers=viewer).status_code == 403
    assert client.get("/api/users", headers=viewer).status_code == 403
    maint = login(client, "maint@hayah.local")
    assert client.post("/api/projects", json={"well_id": 5}, headers=maint).status_code == 403


def test_contractor_sees_only_own_projects(client, seeded):
    h = login(client, "p1@hayah.local")
    wells = {p["well_id"] for p in client.get("/api/projects", headers=h).json()["items"]}
    assert wells == {9001, 9002, 9010}
    assert client.get("/api/projects/9003", headers=h).status_code == 404
    # may update construction progress on own project, but not commercial fields
    assert client.patch("/api/projects/9002", json={"notes": "pump installed"}, headers=h).status_code == 200
    assert client.patch("/api/projects/9002", json={"sale_amount": 1}, headers=h).status_code == 403


def test_admin_creates_user_and_revokes_sessions(client, admin):
    r = client.post("/api/users", headers=admin, json={"email": "new@hayah.local", "full_name": "New", "role": "viewer",
                                                       "password": "Weakpass"})
    assert r.status_code == 422
    r = client.post("/api/users", headers=admin, json={"email": "new@hayah.local", "full_name": "New", "role": "viewer",
                                                       "password": "Strong-Pass-99"})
    assert r.status_code == 201
    h = login(client, "new@hayah.local", "Strong-Pass-99")
    client.patch(f"/api/users/{r.json()['id']}", headers=admin, json={"is_active": False})
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_password_hash_never_returned(client, admin):
    assert "password_hash" not in client.get("/api/users", headers=admin).text
