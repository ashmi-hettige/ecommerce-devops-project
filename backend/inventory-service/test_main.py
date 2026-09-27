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
    r = client.post(URL, json={"name": "eggs", "quantity": 100}, headers=auth)
    assert r.status_code == 201
    pid = r.json()["id"]

    items = client.get(URL, headers=auth).json()
    assert items == [{"id": pid, "name": "eggs", "quantity": 100}]

    assert client.put(f"{URL}/{pid}", json={"quantity": 42}, headers=auth).status_code == 200
    assert client.get(URL, headers=auth).json()[0]["quantity"] == 42

    assert client.delete(f"{URL}/{pid}", headers=auth).status_code == 204
    assert client.get(URL, headers=auth).json() == []


def test_rejects_negative_quantity(client, auth):
    assert client.post(URL, json={"name": "x", "quantity": -1}, headers=auth).status_code == 422


def test_unknown_id_returns_404(client, auth):
    assert client.delete(f"{URL}/not-an-id", headers=auth).status_code == 404
    assert client.delete(f"{URL}/0123456789abcdef01234567", headers=auth).status_code == 404
