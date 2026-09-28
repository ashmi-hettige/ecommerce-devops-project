"""Unit tests for the inventory-service. Run with:  pytest -v"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import main


def make_token(expired: bool = False) -> str:
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=5)
    return jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + delta},
        main.JWT_SECRET, algorithm="HS256",
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["test_db"])
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {make_token()}"}


URL = "/api/inventory/products"


def add(client, auth, **fields):
    body = {"name": "eggs", "quantity": 100, **fields}
    r = client.post(URL, json=body, headers=auth)
    assert r.status_code == 201
    return r.json()["id"]


def test_health(client):
    assert client.get("/health").status_code == 200


def test_requires_token(client):
    assert client.get(URL).status_code in (401, 403)


def test_rejects_expired_token(client):
    r = client.get(URL, headers={"Authorization": f"Bearer {make_token(expired=True)}"})
    assert r.status_code == 401


def test_rejects_forged_token(client):
    bad = jwt.encode({"sub": "admin"}, "a-completely-different-secret-of-32+-bytes", algorithm="HS256")
    assert client.get(URL, headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_full_crud_flow(client, auth):
    pid = add(client, auth, sku="EGG-01", category="Dairy", price=0.5)

    items = client.get(URL, headers=auth).json()
    assert items == [{"id": pid, "name": "eggs", "sku": "EGG-01", "category": "Dairy",
                      "price": 0.5, "quantity": 100, "reorder_level": 10}]

    # partial update: only quantity
    assert client.put(f"{URL}/{pid}", json={"quantity": 42}, headers=auth).status_code == 200
    # partial update: price and name
    r = client.put(f"{URL}/{pid}", json={"price": 0.6, "name": "Eggs (dozen)"}, headers=auth)
    assert r.json()["quantity"] == 42 and r.json()["price"] == 0.6

    assert client.delete(f"{URL}/{pid}", headers=auth).status_code == 204
    assert client.get(URL, headers=auth).json() == []


def test_old_products_without_new_fields_still_load(client, auth):
    """Products saved before price/sku/category existed must not break the API."""
    import asyncio
    asyncio.run(main.db.products.insert_one({"name": "chocolate", "quantity": 5}))
    item = client.get(URL, headers=auth).json()[0]
    assert item["price"] == 0 and item["category"] == "General"


def test_adjust_stock_prevents_overselling(client, auth):
    pid = add(client, auth, quantity=5)
    r = client.post(f"{URL}/{pid}/adjust", json={"delta": -3}, headers=auth)
    assert r.status_code == 200 and r.json()["quantity"] == 2
    r = client.post(f"{URL}/{pid}/adjust", json={"delta": -3}, headers=auth)
    assert r.status_code == 409  # only 2 left
    r = client.post(f"{URL}/{pid}/adjust", json={"delta": 3}, headers=auth)
    assert r.json()["quantity"] == 5


def test_rejects_negative_quantity(client, auth):
    assert client.post(URL, json={"name": "x", "quantity": -1}, headers=auth).status_code == 422


def test_unknown_id_returns_404(client, auth):
    assert client.delete(f"{URL}/not-an-id", headers=auth).status_code == 404
    assert client.delete(f"{URL}/0123456789abcdef01234567", headers=auth).status_code == 404
    r = client.post(f"{URL}/0123456789abcdef01234567/adjust", json={"delta": -1}, headers=auth)
    assert r.status_code == 404
