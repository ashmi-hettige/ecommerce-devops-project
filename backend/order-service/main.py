"""
Order Service (microservice 3 of 3)
-----------------------------------
Responsibility: customer orders, fulfilment and returns.

  pending --pick--> picked --pack--> packed --ship--> shipped --return--> returned

Permissions (from the user's JWT):
  orders:read    view orders                      (all staff)
  orders:create  place orders                     (sales, admin)
  orders:delete  cancel unshipped orders          (sales, admin)
  orders:fulfil  pick / pack / ship               (warehouse, admin)
  orders:return  process returns of shipped ones  (sales, admin)

Service-to-service security: stock is reserved by calling inventory-service
with this service's OWN short-lived token (permission `stock:reserve`),
not the user's token. So a sales agent can place an order without being
allowed to change stock directly.
"""
import os
from datetime import datetime, timedelta, timezone
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
ORDERS_RETURNED = Counter("orders_returned_total", "Orders returned by customers")

FLOW = ["pending", "picked", "packed", "shipped"]


# ---------- Models ----------
class OrderItemIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class OrderIn(BaseModel):
    customer: str = Field(min_length=1, max_length=100)
    ship_to: str = Field(default="", max_length=200)
    items: List[OrderItemIn] = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: Literal["picked", "packed", "shipped"]


class ReturnIn(BaseModel):
    reason: str = Field(default="", max_length=200)


# ---------- Auth ----------
bearer = HTTPBearer()


def current_claims(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require(permission: str):
    def checker(claims: dict = Depends(current_claims)) -> dict:
        if permission not in claims.get("perms", []):
            raise HTTPException(status_code=403, detail="You don't have permission to do that")
        return claims
    return checker


def service_token(on_behalf_of: str) -> str:
    """Short-lived token identifying THIS service to inventory-service."""
    return jwt.encode({
        "sub": "order-service", "perms": ["stock:reserve"], "on_behalf_of": on_behalf_of,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=60),
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------- Calling the inventory-service ----------
async def inventory_call(method: str, path: str, user: str, json: dict | None = None) -> httpx.Response:
    """Single place where this service talks to inventory-service (easy to mock in tests)."""
    try:
        async with httpx.AsyncClient(base_url=INVENTORY_URL, timeout=5) as http:
            return await http.request(method, path, json=json,
                                      headers={"Authorization": f"Bearer {service_token(user)}"})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory service unavailable")


async def move_stock(product_id: str, delta: int, kind: str, user: str, reference: str) -> httpx.Response:
    return await inventory_call("POST", f"/api/inventory/products/{product_id}/reserve", user,
                                json={"delta": delta, "type": kind, "reference": reference})


# ---------- Helpers ----------
def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def to_object_id(order_id: str) -> ObjectId:
    try:
        return ObjectId(order_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Order not found")


async def get_or_404(order_id: str) -> dict:
    doc = await db.orders.find_one({"_id": to_object_id(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return doc


def serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "order_no": doc["order_no"],
        "created_at": iso(doc["created_at"]),
        "created_by": doc.get("created_by", ""),
        "customer": doc["customer"],
        "ship_to": doc.get("ship_to", ""),
        "items": doc["items"],
        "item_count": sum(i["quantity"] for i in doc["items"]),
        "total": doc["total"],
        "status": doc["status"],
        "history": [{**h, "at": iso(h["at"])} for h in doc.get("history", [])],
    }


async def next_order_no() -> int:
    counter = await db.counters.find_one_and_update(
        {"_id": "order_no"}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return 1000 + counter["seq"]


async def restock(doc: dict, kind: str, user: str):
    for line in doc["items"]:
        await move_stock(line["product_id"], line["quantity"], kind, user, f"Order #{doc['order_no']}")


# ---------- Routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "orders"}


@app.get("/api/orders")
async def list_orders(c: dict = Depends(require("orders:read"))):
    docs = await db.orders.find({}).sort("order_no", -1).to_list(5000)
    return [serialize(d) for d in docs]


@app.post("/api/orders", status_code=201)
async def create_order(order: OrderIn, c: dict = Depends(require("orders:create"))):
    user = c["sub"]
    wanted: dict[str, int] = {}  # merge duplicate lines for the same product
    for item in order.items:
        wanted[item.product_id] = wanted.get(item.product_id, 0) + item.quantity

    order_no = await next_order_no()
    ref = f"Order #{order_no}"
    reserved: list[tuple[str, int]] = []
    lines = []

    for pid, qty in wanted.items():
        resp = await move_stock(pid, -qty, "reserve", user, ref)
        if resp.status_code != 200:
            for done_pid, done_qty in reserved:  # roll back what was already reserved
                await move_stock(done_pid, done_qty, "release", user, f"{ref} (rolled back)")
            if resp.status_code == 409:
                ORDERS_REJECTED.inc()
                name = (await inventory_call("GET", f"/api/inventory/products/{pid}", user)).json().get("name", pid)
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
        "order_no": order_no, "created_at": now(), "created_by": user,
        "customer": order.customer, "ship_to": order.ship_to,
        "items": lines, "total": total, "status": "pending",
        "history": [{"status": "pending", "by": user, "at": now()}],
    }
    result = await db.orders.insert_one(doc)
    doc["_id"] = result.inserted_id

    ORDERS_CREATED.inc()
    ORDER_REVENUE.inc(total)
    return serialize(doc)


@app.patch("/api/orders/{order_id}/status")
async def update_status(order_id: str, body: StatusUpdate, c: dict = Depends(require("orders:fulfil"))):
    doc = await get_or_404(order_id)
    if doc["status"] not in FLOW or FLOW.index(body.status) != FLOW.index(doc["status"]) + 1:
        raise HTTPException(status_code=409, detail=f"Cannot move order from {doc['status']} to {body.status}")
    entry = {"status": body.status, "by": c["sub"], "at": now()}
    await db.orders.update_one({"_id": doc["_id"]},
                               {"$set": {"status": body.status}, "$push": {"history": entry}})
    return serialize(await get_or_404(order_id))


@app.post("/api/orders/{order_id}/return")
async def return_order(order_id: str, body: ReturnIn, c: dict = Depends(require("orders:return"))):
    doc = await get_or_404(order_id)
    if doc["status"] != "shipped":
        raise HTTPException(status_code=409, detail="Only shipped orders can be returned")
    await restock(doc, "return", c["sub"])
    entry = {"status": "returned", "by": c["sub"], "at": now(), "note": body.reason}
    await db.orders.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "returned"}, "$push": {"history": entry}})
    ORDERS_RETURNED.inc()
    return serialize(await get_or_404(order_id))


@app.delete("/api/orders/{order_id}", status_code=204)
async def delete_order(order_id: str, c: dict = Depends(require("orders:delete"))):
    doc = await get_or_404(order_id)
    if doc["status"] == "shipped":
        raise HTTPException(status_code=409, detail="Shipped orders can't be cancelled. Process a return instead.")
    if doc["status"] in ("pending", "picked", "packed"):
        await restock(doc, "release", c["sub"])  # cancelled before shipping: stock goes back
    await db.orders.delete_one({"_id": doc["_id"]})
