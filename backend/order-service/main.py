"""
Order Service (microservice 3 of 3)
-----------------------------------
Responsibility: customer orders and their fulfilment status
(pending -> picked -> shipped).

This is the service that talks to another service: when an order is
placed it calls the inventory-service over HTTP to reserve stock, and
when an unshipped order is deleted it puts that stock back. The user's
JWT is forwarded, so inventory-service still checks who is asking.
"""
import os
from datetime import datetime, timezone
from typing import List, Literal

import httpx
import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

# ---------- Configuration ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "inventory_db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-before-deploying!!")
JWT_ALGORITHM = "HS256"
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://127.0.0.1:8002")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Order Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, include_in_schema=False)

# Business metrics for Grafana (on top of the HTTP metrics above)
ORDERS_CREATED = Counter("orders_created_total", "Orders successfully placed")
ORDER_REVENUE = Counter("orders_revenue_total", "Sum of order totals placed")
ORDERS_REJECTED = Counter("orders_rejected_stock_total", "Orders rejected for insufficient stock")

STATUS_FLOW = ["pending", "picked", "shipped"]


# ---------- Models ----------
class OrderItemIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class OrderIn(BaseModel):
    customer: str = Field(min_length=1, max_length=100)
    ship_to: str = Field(default="", max_length=200)
    items: List[OrderItemIn] = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: Literal["pending", "picked", "shipped"]


# ---------- Auth ----------
bearer = HTTPBearer()


def require_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Validates the JWT and returns the raw token so it can be forwarded."""
    try:
        jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return creds.credentials


# ---------- Calling the inventory-service ----------
async def inventory_call(method: str, path: str, token: str, json: dict | None = None) -> httpx.Response:
    """Single place where this service talks to inventory-service (easy to mock in tests)."""
    try:
        async with httpx.AsyncClient(base_url=INVENTORY_URL, timeout=5) as http:
            return await http.request(method, path, json=json,
                                      headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory service unavailable")


async def adjust_stock(product_id: str, delta: int, token: str) -> httpx.Response:
    return await inventory_call("POST", f"/api/inventory/products/{product_id}/adjust",
                                token, json={"delta": delta})


# ---------- Helpers ----------
def to_object_id(order_id: str) -> ObjectId:
    try:
        return ObjectId(order_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Order not found")


def serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "order_no": doc["order_no"],
        "created_at": doc["created_at"].replace(tzinfo=timezone.utc).isoformat(),
        "customer": doc["customer"],
        "ship_to": doc.get("ship_to", ""),
        "items": doc["items"],
        "item_count": sum(i["quantity"] for i in doc["items"]),
        "total": doc["total"],
        "status": doc["status"],
    }


async def next_order_no() -> int:
    counter = await db.counters.find_one_and_update(
        {"_id": "order_no"}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return 1000 + counter["seq"]


# ---------- Routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "orders"}


@app.get("/api/orders")
async def list_orders(token: str = Depends(require_user)):
    docs = await db.orders.find({}).sort("order_no", -1).to_list(5000)
    return [serialize(d) for d in docs]


@app.post("/api/orders", status_code=201)
async def create_order(order: OrderIn, token: str = Depends(require_user)):
    # Merge duplicate lines for the same product
    wanted: dict[str, int] = {}
    for item in order.items:
        wanted[item.product_id] = wanted.get(item.product_id, 0) + item.quantity

    reserved: list[tuple[str, int]] = []
    lines = []

    async def rollback():
        for pid, qty in reserved:
            await adjust_stock(pid, qty, token)

    for pid, qty in wanted.items():
        resp = await adjust_stock(pid, -qty, token)
        if resp.status_code != 200:
            await rollback()
            if resp.status_code == 409:
                ORDERS_REJECTED.inc()
                name = (await inventory_call("GET", f"/api/inventory/products/{pid}", token)).json().get("name", pid)
                raise HTTPException(status_code=409, detail=f"Not enough stock for {name}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Product not found")
            raise HTTPException(status_code=502, detail="Inventory service error")
        reserved.append((pid, qty))
        product = resp.json()
        lines.append({"product_id": pid, "name": product["name"], "sku": product.get("sku", ""),
                      "price": product.get("price", 0), "quantity": qty})

    total = round(sum(line["price"] * line["quantity"] for line in lines), 2)
    doc = {
        "order_no": await next_order_no(),
        "created_at": datetime.now(timezone.utc),
        "customer": order.customer,
        "ship_to": order.ship_to,
        "items": lines,
        "total": total,
        "status": "pending",
    }
    result = await db.orders.insert_one(doc)
    doc["_id"] = result.inserted_id

    ORDERS_CREATED.inc()
    ORDER_REVENUE.inc(total)
    return serialize(doc)


@app.patch("/api/orders/{order_id}/status")
async def update_status(order_id: str, body: StatusUpdate, token: str = Depends(require_user)):
    doc = await db.orders.find_one({"_id": to_object_id(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    if STATUS_FLOW.index(body.status) != STATUS_FLOW.index(doc["status"]) + 1:
        raise HTTPException(status_code=409,
                            detail=f"Cannot move order from {doc['status']} to {body.status}")
    await db.orders.update_one({"_id": doc["_id"]}, {"$set": {"status": body.status}})
    doc["status"] = body.status
    return serialize(doc)


@app.delete("/api/orders/{order_id}", status_code=204)
async def delete_order(order_id: str, token: str = Depends(require_user)):
    doc = await db.orders.find_one({"_id": to_object_id(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    # Cancelling an order that hasn't shipped puts its stock back
    if doc["status"] != "shipped":
        for line in doc["items"]:
            await adjust_stock(line["product_id"], line["quantity"], token)
    await db.orders.delete_one({"_id": doc["_id"]})
