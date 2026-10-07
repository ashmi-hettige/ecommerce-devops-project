"""
Inventory Service (microservice 2 of 3)
---------------------------------------
Responsibility: the product catalogue, stock levels and a stock movement log.

Access is controlled by the permissions inside the JWT (issued by auth-service):
  products:read   view products              (everyone)
  products:write  create / edit / delete     (admin, inventory manager)
  products:price  set or change prices       (admin, inventory manager)
  stock:adjust    free +/- corrections       (admin, inventory manager)
  stock:receive   receive deliveries         (+ warehouse staff)
  stock:count     record a stock count       (+ warehouse staff)
  stock:reserve   reserve/release for orders (order-service's own service token)
Every stock change is written to the `movements` collection (who, what, when, why).
"""
import os
from datetime import datetime, timezone
from typing import Literal, Optional

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# ---------- Configuration ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "inventory_db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-before-deploying!!")
JWT_ALGORITHM = "HS256"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Inventory Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, include_in_schema=False)


# ---------- Models ----------
class Product(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sku: str = Field(default="", max_length=40)
    category: str = Field(default="General", max_length=40)
    price: float = Field(default=0, ge=0)
    quantity: int = Field(ge=0)
    reorder_level: int = Field(default=10, ge=0)


class ProductUpdate(BaseModel):
    """All fields optional: send only what changes."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    sku: Optional[str] = Field(default=None, max_length=40)
    category: Optional[str] = Field(default=None, max_length=40)
    price: Optional[float] = Field(default=None, ge=0)
    quantity: Optional[int] = Field(default=None, ge=0)
    reorder_level: Optional[int] = Field(default=None, ge=0)


class StockAdjust(BaseModel):
    delta: int
    note: str = Field(default="", max_length=200)


class StockReceive(BaseModel):
    quantity: int = Field(gt=0)
    reference: str = Field(default="", max_length=100)  # supplier / delivery note / PO number


class StockCount(BaseModel):
    counted: int = Field(ge=0)
    note: str = Field(default="", max_length=200)


class StockReserve(BaseModel):
    delta: int  # negative = reserve for an order, positive = release back
    type: Literal["reserve", "release", "return"] = "reserve"
    reference: str = Field(default="", max_length=100)


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


# ---------- Helpers ----------
def to_object_id(product_id: str) -> ObjectId:
    try:
        return ObjectId(product_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Product not found")


def serialize(doc: dict) -> dict:
    # .get() defaults keep products created before these fields existed working
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "sku": doc.get("sku", ""),
        "category": doc.get("category", "General"),
        "price": doc.get("price", 0),
        "quantity": doc["quantity"],
        "reorder_level": doc.get("reorder_level", 10),
    }


async def get_or_404(product_id: str) -> dict:
    doc = await db.products.find_one({"_id": to_object_id(product_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return doc


async def log_movement(product: dict, kind: str, delta: int, user: str, reference: str = ""):
    await db.movements.insert_one({
        "product_id": str(product["_id"]), "product_name": product["name"],
        "type": kind, "delta": delta, "quantity_after": product["quantity"],
        "reference": reference, "user": user, "at": datetime.now(timezone.utc),
    })


async def change_stock(product_id: str, delta: int, kind: str, user: str, reference: str = "") -> dict:
    """Atomic stock change. Taking out more than is available fails with 409,
    so two orders can never oversell the same item."""
    query = {"_id": to_object_id(product_id)}
    if delta < 0:
        query["quantity"] = {"$gte": -delta}
    result = await db.products.update_one(query, {"$inc": {"quantity": delta}})
    if result.matched_count == 0:
        await get_or_404(product_id)  # 404 if it doesn't exist at all
        raise HTTPException(status_code=409, detail="Insufficient stock")
    product = await get_or_404(product_id)
    await log_movement(product, kind, delta, user, reference)
    return serialize(product)


# ---------- Routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "inventory"}


@app.get("/api/inventory/products")
async def list_products(c: dict = Depends(require("products:read"))):
    docs = await db.products.find({}).to_list(5000)
    return [serialize(d) for d in docs]


@app.get("/api/inventory/products/{product_id}")
async def get_product(product_id: str, c: dict = Depends(current_claims)):
    if not {"products:read", "stock:reserve"} & set(c.get("perms", [])):
        raise HTTPException(status_code=403, detail="You don't have permission to do that")
    return serialize(await get_or_404(product_id))


@app.post("/api/inventory/products", status_code=201)
async def add_product(product: Product, c: dict = Depends(require("products:write"))):
    if product.price and "products:price" not in c["perms"]:
        raise HTTPException(status_code=403, detail="You don't have permission to set prices")
    result = await db.products.insert_one(product.model_dump())
    doc = await get_or_404(str(result.inserted_id))
    await log_movement(doc, "create", doc["quantity"], c["sub"], "New product")
    return serialize(doc)


@app.put("/api/inventory/products/{product_id}")
async def update_product(product_id: str, body: ProductUpdate, c: dict = Depends(require("products:write"))):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update")
    before = await get_or_404(product_id)
    if "price" in changes and changes["price"] != before.get("price", 0) and "products:price" not in c["perms"]:
        raise HTTPException(status_code=403, detail="You don't have permission to change prices")
    await db.products.update_one({"_id": before["_id"]}, {"$set": changes})
    after = await get_or_404(product_id)
    if "quantity" in changes and changes["quantity"] != before["quantity"]:
        await log_movement(after, "edit", changes["quantity"] - before["quantity"], c["sub"], "Edited in product form")
    return serialize(after)


@app.post("/api/inventory/products/{product_id}/adjust")
async def adjust_stock(product_id: str, body: StockAdjust, c: dict = Depends(require("stock:adjust"))):
    return await change_stock(product_id, body.delta, "adjust", c["sub"], body.note)


@app.post("/api/inventory/products/{product_id}/receive")
async def receive_stock(product_id: str, body: StockReceive, c: dict = Depends(require("stock:receive"))):
    return await change_stock(product_id, body.quantity, "receive", c["sub"], body.reference)


@app.post("/api/inventory/products/{product_id}/count")
async def count_stock(product_id: str, body: StockCount, c: dict = Depends(require("stock:count"))):
    before = await get_or_404(product_id)
    await db.products.update_one({"_id": before["_id"]}, {"$set": {"quantity": body.counted}})
    after = await get_or_404(product_id)
    await log_movement(after, "count", body.counted - before["quantity"], c["sub"],
                       body.note or f"Counted {body.counted} (system had {before['quantity']})")
    return serialize(after)


@app.post("/api/inventory/products/{product_id}/reserve")
async def reserve_stock(product_id: str, body: StockReserve, c: dict = Depends(require("stock:reserve"))):
    """Internal: only the order-service's service token has stock:reserve."""
    return await change_stock(product_id, body.delta, body.type, c.get("on_behalf_of", c["sub"]), body.reference)


@app.delete("/api/inventory/products/{product_id}", status_code=204)
async def delete_product(product_id: str, c: dict = Depends(require("products:write"))):
    result = await db.products.delete_one({"_id": to_object_id(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")


@app.get("/api/inventory/movements")
async def list_movements(limit: int = 100, c: dict = Depends(require("products:read"))):
    docs = await db.movements.find({}).sort("at", -1).to_list(min(max(limit, 1), 500))
    return [{
        "id": str(d["_id"]), "product_id": d["product_id"], "product_name": d["product_name"],
        "type": d["type"], "delta": d["delta"], "quantity_after": d["quantity_after"],
        "reference": d.get("reference", ""), "user": d.get("user", ""),
        "at": d["at"].replace(tzinfo=timezone.utc).isoformat(),
    } for d in docs]
