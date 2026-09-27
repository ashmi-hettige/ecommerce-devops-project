"""Unit tests for the auth-service. Run with:  pytest -v
Uses an in-memory fake MongoDB, so no database needs to be running
(this is what lets the Jenkins 'Test' stage run anywhere)."""
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


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "auth"


def test_login_success_returns_valid_jwt(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    payload = jwt.decode(token, main.JWT_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "admin"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_metrics_endpoint(client):
    assert client.get("/metrics").status_code == 200
