"""Unit tests for the inventory-service. Run with:  pytest -v"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import main

# Permission sets as issued by auth-service
PERMS = {
    "admin": ["products:read", "products:write", "products:price", "stock:adjust",
              "stock:receive", "stock:count"],
    "manager": ["products:read", "products:write", "products:price", "stock:adjust",
                "stock:receive", "stock:count"],
    "warehouse": ["products:read", "stock:receive", "stock:count"],
    "sales": ["products:read"],
    "order-service": ["stock:reserve"],
}
URL = "/api/inventory/products"


def make_token(who="admin", expired=False, secret=None):
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=5)
    return jwt.encode({"sub": who, "perms": PERMS[who], "exp": datetime.now(timezone.utc) + delta},
                      secret or main.JWT_SECRET, algorithm="HS256")


def as_(who):
    return {"Authorization": f"Bearer {make_token(who)}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["test_db"])
    with TestClient(main.app) as c:
        yield c


def add(client, **fields):
    body = {"name": "eggs", "quantity": 100, "price": 50, **fields}
    r = client.post(URL, json=body, headers=as_("admin"))
    assert r.status_code == 201
    return r.json()["id"]


def test_health(client):
    assert client.get("/health").status_code == 200


def test_requires_valid_token(client):
    assert client.get(URL).status_code in (401, 403)
    expired = {"Authorization": f"Bearer {make_token(expired=True)}"}
    assert client.get(URL, headers=expired).status_code == 401
    forged = {"Authorization": f"Bearer {make_token(secret='a-completely-different-secret-of-32+-bytes')}"}
    assert client.get(URL, headers=forged).status_code == 401


def test_everyone_can_view_products(client):
    add(client)
    for who in ["admin", "manager", "warehouse", "sales"]:
        assert client.get(URL, headers=as_(who)).status_code == 200


def test_full_crud_flow_as_manager(client):
    r = client.post(URL, json={"name": "eggs", "sku": "EGG-01", "category": "Dairy",
                               "price": 0.5, "quantity": 100}, headers=as_("manager"))
    assert r.status_code == 201
    pid = r.json()["id"]
    r = client.put(f"{URL}/{pid}", json={"price": 0.6, "name": "Eggs (dozen)"}, headers=as_("manager"))
    assert r.json()["price"] == 0.6
    assert client.delete(f"{URL}/{pid}", headers=as_("manager")).status_code == 204


def test_warehouse_cannot_change_prices_or_catalogue(client):
    pid = add(client)
    assert client.put(f"{URL}/{pid}", json={"price": 1}, headers=as_("warehouse")).status_code == 403
    assert client.post(URL, json={"name": "x", "quantity": 1}, headers=as_("warehouse")).status_code == 403
    assert client.delete(f"{URL}/{pid}", headers=as_("warehouse")).status_code == 403
    assert client.post(f"{URL}/{pid}/adjust", json={"delta": 5}, headers=as_("warehouse")).status_code == 403


def test_warehouse_can_receive_and_count(client):
    pid = add(client, quantity=10)
    r = client.post(f"{URL}/{pid}/receive", json={"quantity": 20, "reference": "PO-77"}, headers=as_("warehouse"))
    assert r.status_code == 200 and r.json()["quantity"] == 30
    r = client.post(f"{URL}/{pid}/count", json={"counted": 28}, headers=as_("warehouse"))
    assert r.json()["quantity"] == 28


def test_sales_cannot_touch_stock(client):
    pid = add(client)
    for path, body in [("receive", {"quantity": 1}), ("count", {"counted": 1}), ("adjust", {"delta": 1})]:
        assert client.post(f"{URL}/{pid}/{path}", json=body, headers=as_("sales")).status_code == 403


def test_only_service_token_can_reserve(client):
    pid = add(client, quantity=5)
    body = {"delta": -3, "type": "reserve", "reference": "Order #1001"}
    assert client.post(f"{URL}/{pid}/reserve", json=body, headers=as_("admin")).status_code == 403
    r = client.post(f"{URL}/{pid}/reserve", json=body, headers=as_("order-service"))
    assert r.status_code == 200 and r.json()["quantity"] == 2
    r = client.post(f"{URL}/{pid}/reserve", json=body, headers=as_("order-service"))
    assert r.status_code == 409  # only 2 left: no overselling


def test_movements_are_logged_with_user(client):
    pid = add(client, quantity=10)
    client.post(f"{URL}/{pid}/receive", json={"quantity": 5, "reference": "Supplier A"}, headers=as_("warehouse"))
    client.post(f"{URL}/{pid}/count", json={"counted": 12}, headers=as_("warehouse"))
    log = client.get("/api/inventory/movements", headers=as_("sales")).json()
    kinds = [(m["type"], m["delta"], m["user"]) for m in log]
    assert ("receive", 5, "warehouse") in kinds
    assert ("count", -3, "warehouse") in kinds
    assert ("create", 10, "admin") in kinds


def test_old_products_without_new_fields_still_load(client):
    import asyncio
    asyncio.run(main.db.products.insert_one({"name": "chocolate", "quantity": 5}))
    item = client.get(URL, headers=as_("sales")).json()[0]
    assert item["price"] == 0 and item["category"] == "General"


def test_validation_and_404(client):
    assert client.post(URL, json={"name": "x", "quantity": -1}, headers=as_("admin")).status_code == 422
    assert client.delete(f"{URL}/not-an-id", headers=as_("admin")).status_code == 404
    r = client.post(f"{URL}/0123456789abcdef01234567/receive", json={"quantity": 1}, headers=as_("admin"))
    assert r.status_code == 404
