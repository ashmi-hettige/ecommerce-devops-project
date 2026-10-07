"""Unit tests for the auth-service. Run with:  pytest -v
Uses an in-memory fake MongoDB, so no database needs to be running."""
import jwt
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["test_db"])
    with TestClient(main.app) as c:  # "with" runs the startup seeding
        yield c


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def auth_as(client, username, password):
    return {"Authorization": f"Bearer {login(client, username, password).json()['access_token']}"}


def claims(resp):
    return jwt.decode(resp.json()["access_token"], main.JWT_SECRET, algorithms=["HS256"])


def test_health(client):
    assert client.get("/health").json()["service"] == "auth"


def test_token_carries_role_and_permissions(client):
    c = claims(login(client, "admin", main.ADMIN_PASSWORD))
    assert c["role"] == "admin" and "users:manage" in c["perms"]
    c = claims(login(client, "warehouse", "Warehouse@123"))
    assert c["role"] == "warehouse"
    assert "stock:receive" in c["perms"] and "products:price" not in c["perms"]


def test_wrong_password_and_unknown_user_look_the_same(client):
    a = login(client, "admin", "wrong")
    b = login(client, "nobody", "wrong")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_locks_after_repeated_failures(client):
    for _ in range(main.MAX_FAILED_ATTEMPTS):
        assert login(client, "sales", "wrong").status_code == 401
    r = login(client, "sales", "Sales@123")  # correct password, but locked
    assert r.status_code == 423
    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    assert client.post("/api/auth/users/sales/unlock", headers=admin).status_code == 200
    assert login(client, "sales", "Sales@123").status_code == 200


def test_only_admin_can_manage_users(client):
    for user, pw in [("manager", "Manager@123"), ("warehouse", "Warehouse@123"), ("sales", "Sales@123")]:
        assert client.get("/api/auth/users", headers=auth_as(client, user, pw)).status_code == 403
    assert client.get("/api/auth/users", headers=auth_as(client, "admin", main.ADMIN_PASSWORD)).status_code == 200


def test_new_user_must_change_temporary_password(client):
    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    weak = client.post("/api/auth/users", headers=admin,
                       json={"username": "kamal", "role": "warehouse", "password": "short"})
    assert weak.status_code == 422

    r = client.post("/api/auth/users", headers=admin,
                    json={"username": "kamal", "full_name": "Kamal", "role": "warehouse", "password": "Temp1234"})
    assert r.status_code == 201 and r.json()["must_change_password"]

    first = login(client, "kamal", "Temp1234")
    assert claims(first)["pwd_change"] is True
    hdr = {"Authorization": f"Bearer {first.json()['access_token']}"}
    bad = client.post("/api/auth/change-password", headers=hdr,
                      json={"current_password": "Temp1234", "new_password": "nonumbers"})
    assert bad.status_code == 422
    ok = client.post("/api/auth/change-password", headers=hdr,
                     json={"current_password": "Temp1234", "new_password": "Kamal2026!"})
    assert ok.status_code == 200 and claims(ok)["pwd_change"] is False
    assert login(client, "kamal", "Kamal2026!").status_code == 200


def test_disabled_user_cannot_log_in(client):
    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    client.patch("/api/auth/users/sales", headers=admin, json={"active": False})
    assert login(client, "sales", "Sales@123").status_code == 403


def test_role_change_takes_effect_on_next_login(client):
    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    client.patch("/api/auth/users/sales", headers=admin, json={"role": "inventory_manager"})
    assert claims(login(client, "sales", "Sales@123"))["role"] == "inventory_manager"


def test_cannot_remove_last_or_own_admin(client):
    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    r = client.patch("/api/auth/users/admin", headers=admin, json={"active": False})
    assert r.status_code == 409
    r = client.patch("/api/auth/users/admin", headers=admin, json={"role": "sales"})
    assert r.status_code == 409


def test_me_and_metrics(client):
    me = client.get("/api/auth/me", headers=auth_as(client, "manager", "Manager@123")).json()
    assert me["role"] == "inventory_manager" and "reports:read" in me["permissions"]
    assert "auth_login_total" in client.get("/metrics").text


def test_register_needs_admin_approval(client):
    weak = client.post("/api/auth/register", json={"username": "nuwan", "password": "abc"})
    assert weak.status_code == 422
    r = client.post("/api/auth/register", json={"username": "nuwan", "full_name": "Nuwan", "password": "Nuwan2026x"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"username": "nuwan", "password": "Other2026x"}).status_code == 409

    # Registered but not approved: cannot sign in
    pending = login(client, "nuwan", "Nuwan2026x")
    assert pending.status_code == 403 and "approve" in pending.json()["detail"]

    admin = auth_as(client, "admin", main.ADMIN_PASSWORD)
    listed = {u["username"]: u for u in client.get("/api/auth/users", headers=admin).json()}
    assert listed["nuwan"]["pending"] is True

    # Admin approves by assigning a role
    client.patch("/api/auth/users/nuwan", headers=admin, json={"role": "sales"})
    ok = login(client, "nuwan", "Nuwan2026x")
    assert ok.status_code == 200 and claims(ok)["role"] == "sales"


def test_register_cannot_choose_a_role(client):
    r = client.post("/api/auth/register", json={"username": "sneaky", "password": "Sneaky2026", "role": "admin"})
    assert r.status_code == 201  # extra "role" field is ignored
    assert login(client, "sneaky", "Sneaky2026").status_code == 403


def test_admin_password_is_strong():
    assert main.password_problems(main.ADMIN_PASSWORD, "admin") == []


def test_old_weak_admin_password_is_replaced(monkeypatch):
    """A database that still has admin/admin123 is upgraded on startup."""
    import asyncio
    db = AsyncMongoMockClient()["legacy_db"]
    asyncio.run(db.users.insert_one({"username": "admin", "password": main.hash_password("admin123")}))
    monkeypatch.setattr(main, "db", db)
    with TestClient(main.app) as c:
        assert login(c, "admin", "admin123").status_code == 401
        assert login(c, "admin", main.ADMIN_PASSWORD).status_code == 200
