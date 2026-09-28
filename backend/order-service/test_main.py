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


class FakeInventory:
    def __init__(self):
        self.products = {
            "p1": {"id": "p1", "name": "Eggs", "sku": "EGG-01", "price": 2.5, "quantity": 10},
            "p2": {"id": "p2", "name": "Chocolate", "sku": "CHO-01", "price": 4.0, "quantity": 1},
        }

    async def call(self, method, path, token, json=None):
        pid = path.split("/")[4]
        product = self.products.get(pid)
        if product is None:
            return httpx.Response(404, json={"detail": "Product not found"})
        if path.endswith("/adjust"):
            delta = json["delta"]
            if product["quantity"] + delta < 0:
                return httpx.Response(409, json={"detail": "Insufficient stock"})
            product["quantity"] += delta
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


@pytest.fixture
def auth():
    token = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       main.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def place(client, auth, items, customer="Nimal Perera"):
    return client.post(URL, json={"customer": customer, "ship_to": "Galle", "items": items}, headers=auth)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_requires_token(client):
    assert client.get(URL).status_code in (401, 403)


def test_create_order_reserves_stock_and_totals(client, auth, inv):
    r = place(client, auth, [{"product_id": "p1", "quantity": 3}])
    assert r.status_code == 201
    order = r.json()
    assert order["order_no"] == 1001
    assert order["total"] == 7.5
    assert order["status"] == "pending"
    assert inv.products["p1"]["quantity"] == 7

    assert place(client, auth, [{"product_id": "p1", "quantity": 1}]).json()["order_no"] == 1002


def test_insufficient_stock_rolls_back(client, auth, inv):
    r = place(client, auth, [{"product_id": "p1", "quantity": 2},
                             {"product_id": "p2", "quantity": 5}])
    assert r.status_code == 409
    assert "Chocolate" in r.json()["detail"]
    assert inv.products["p1"]["quantity"] == 10  # the eggs were put back
    assert client.get(URL, headers=auth).json() == []


def test_status_flow_is_forward_only(client, auth):
    oid = place(client, auth, [{"product_id": "p1", "quantity": 1}]).json()["id"]
    s = f"{URL}/{oid}/status"
    assert client.patch(s, json={"status": "shipped"}, headers=auth).status_code == 409
    assert client.patch(s, json={"status": "picked"}, headers=auth).json()["status"] == "picked"
    assert client.patch(s, json={"status": "shipped"}, headers=auth).json()["status"] == "shipped"
    assert client.patch(s, json={"status": "pending"}, headers=auth).status_code == 409


def test_delete_unshipped_order_restocks(client, auth, inv):
    oid = place(client, auth, [{"product_id": "p1", "quantity": 4}]).json()["id"]
    assert inv.products["p1"]["quantity"] == 6
    assert client.delete(f"{URL}/{oid}", headers=auth).status_code == 204
    assert inv.products["p1"]["quantity"] == 10


def test_unknown_product_404(client, auth):
    assert place(client, auth, [{"product_id": "nope", "quantity": 1}]).status_code == 404


def test_business_metrics_exposed(client, auth):
    place(client, auth, [{"product_id": "p1", "quantity": 1}])
    metrics = client.get("/metrics").text
    assert "orders_created_total" in metrics
    assert "orders_revenue_total" in metrics
