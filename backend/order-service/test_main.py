"""Unit tests for the order-service. Run with:  pytest -v
The inventory-service is replaced by a small in-memory fake, so these
tests need neither MongoDB nor the other services to be running."""
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import main

URL = "/api/orders"
PERMS = {
    "admin": ["orders:read", "orders:create", "orders:delete", "orders:fulfil", "orders:return"],
    "sales": ["orders:read", "orders:create", "orders:delete", "orders:return"],
    "warehouse": ["orders:read", "orders:fulfil"],
    "manager": ["orders:read"],
}


def as_(who):
    token = jwt.encode({"sub": who, "perms": PERMS[who], "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       main.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


class FakeInventory:
    """Behaves like inventory-service and records who called it."""
    def __init__(self):
        self.products = {
            "p1": {"id": "p1", "name": "Eggs", "sku": "EGG-01", "price": 2.5, "quantity": 10},
            "p2": {"id": "p2", "name": "Chocolate", "sku": "CHO-01", "price": 4.0, "quantity": 1},
        }
        self.callers = []

    async def call(self, method, path, user, json=None):
        self.callers.append(user)
        pid = path.split("/")[4]
        product = self.products.get(pid)
        if product is None:
            return httpx.Response(404, json={"detail": "Product not found"})
        if path.endswith("/reserve"):
            if product["quantity"] + json["delta"] < 0:
                return httpx.Response(409, json={"detail": "Insufficient stock"})
            product["quantity"] += json["delta"]
        return httpx.Response(200, json=product)


@pytest.fixture
def inv(monkeypatch):
    fake = FakeInventory()
    monkeypatch.setattr(main, "inventory_call", fake.call)
    return fake


@pytest.fixture
def client(monkeypatch, inv):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["test_db"])
    with TestClient(main.app) as c:
        yield c


def place(client, items, who="sales"):
    return client.post(URL, json={"customer": "Nimal Perera", "ship_to": "Galle", "items": items}, headers=as_(who))


def status(client, oid, new, who="warehouse"):
    return client.patch(f"{URL}/{oid}/status", json={"status": new}, headers=as_(who))


def test_health(client):
    assert client.get("/health").status_code == 200


def test_requires_token(client):
    assert client.get(URL).status_code in (401, 403)


def test_service_token_is_scoped():
    claims = jwt.decode(main.service_token("sales"), main.JWT_SECRET, algorithms=["HS256"])
    assert claims["perms"] == ["stock:reserve"] and claims["on_behalf_of"] == "sales"


def test_sales_places_order_and_stock_is_reserved(client, inv):
    r = place(client, [{"product_id": "p1", "quantity": 3}])
    assert r.status_code == 201
    order = r.json()
    assert order["order_no"] == 1001 and order["total"] == 7.5 and order["created_by"] == "sales"
    assert inv.products["p1"]["quantity"] == 7
    assert inv.callers[0] == "sales"  # reservation made on behalf of the user


def test_warehouse_and_manager_cannot_place_orders(client):
    assert place(client, [{"product_id": "p1", "quantity": 1}], who="warehouse").status_code == 403
    assert place(client, [{"product_id": "p1", "quantity": 1}], who="manager").status_code == 403


def test_insufficient_stock_rolls_back(client, inv):
    r = place(client, [{"product_id": "p1", "quantity": 2}, {"product_id": "p2", "quantity": 5}])
    assert r.status_code == 409 and "Chocolate" in r.json()["detail"]
    assert inv.products["p1"]["quantity"] == 10
    assert client.get(URL, headers=as_("sales")).json() == []


def test_warehouse_fulfils_pick_pack_ship_in_order(client):
    oid = place(client, [{"product_id": "p1", "quantity": 1}]).json()["id"]
    assert status(client, oid, "shipped").status_code == 409      # can't skip steps
    assert status(client, oid, "picked", who="sales").status_code == 403  # sales can't fulfil
    for step in ["picked", "packed", "shipped"]:
        assert status(client, oid, step).json()["status"] == step
    history = client.get(URL, headers=as_("manager")).json()[0]["history"]
    assert [h["status"] for h in history] == ["pending", "picked", "packed", "shipped"]
    assert history[-1]["by"] == "warehouse"


def test_return_restocks_and_only_after_shipping(client, inv):
    oid = place(client, [{"product_id": "p1", "quantity": 4}]).json()["id"]
    ret = f"{URL}/{oid}/return"
    assert client.post(ret, json={}, headers=as_("sales")).status_code == 409  # not shipped yet
    for step in ["picked", "packed", "shipped"]:
        status(client, oid, step)
    assert client.post(ret, json={}, headers=as_("warehouse")).status_code == 403
    r = client.post(ret, json={"reason": "Damaged"}, headers=as_("sales"))
    assert r.json()["status"] == "returned"
    assert inv.products["p1"]["quantity"] == 10


def test_cancel_unshipped_restocks_but_shipped_cannot_be_cancelled(client, inv):
    oid = place(client, [{"product_id": "p1", "quantity": 4}]).json()["id"]
    assert client.delete(f"{URL}/{oid}", headers=as_("warehouse")).status_code == 403
    assert client.delete(f"{URL}/{oid}", headers=as_("sales")).status_code == 204
    assert inv.products["p1"]["quantity"] == 10

    oid = place(client, [{"product_id": "p1", "quantity": 1}]).json()["id"]
    for step in ["picked", "packed", "shipped"]:
        status(client, oid, step)
    assert client.delete(f"{URL}/{oid}", headers=as_("sales")).status_code == 409


def test_unknown_product_404(client):
    assert place(client, [{"product_id": "nope", "quantity": 1}]).status_code == 404


def test_business_metrics_exposed(client):
    place(client, [{"product_id": "p1", "quantity": 1}])
    metrics = client.get("/metrics").text
    for name in ["orders_created_total", "orders_revenue_total", "orders_returned_total"]:
        assert name in metrics
