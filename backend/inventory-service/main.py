"""
Inventory Service (microservice 2 of 3)
---------------------------------------
Responsibility: the product catalogue and stock levels in MongoDB.
Every /api/inventory route requires a valid JWT issued by the auth-service
(shared JWT_SECRET). The order-service calls the /adjust endpoint to
reserve or release stock when orders are created or cancelled.
"""
import os
from typing import Optional

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
    """All fields optional: send only what changes (e.g. just quantity)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    sku: Optional[str] = Field(default=None, max_length=40)
    category: Optional[str] = Field(default=None, max_length=40)
    price: Optional[float] = Field(default=None, ge=0)
    quantity: Optional[int] = Field(default=None, ge=0)
    reorder_level: Optional[int] = Field(default=None, ge=0)


class StockAdjust(BaseModel):
    delta: int  # negative = take stock out, positive = put stock back


# ---------- Auth dependency ----------
bearer = HTTPBearer()


def require_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Rejects the request unless it carries a valid, unexpired JWT."""
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]


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


# ---------- Routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "inventory"}


@app.get("/api/inventory/products")
async def list_products(user: str = Depends(require_user)):
    docs = await db.products.find({}).to_list(5000)
    return [serialize(d) for d in docs]


@app.get("/api/inventory/products/{product_id}")
async def get_product(product_id: str, user: str = Depends(require_user)):
    return serialize(await get_or_404(product_id))


@app.post("/api/inventory/products", status_code=201)
async def add_product(product: Product, user: str = Depends(require_user)):
    result = await db.products.insert_one(product.model_dump())
    return {"id": str(result.inserted_id), **product.model_dump()}


@app.put("/api/inventory/products/{product_id}")
async def update_product(product_id: str, body: ProductUpdate, user: str = Depends(require_user)):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update")
    result = await db.products.update_one({"_id": to_object_id(product_id)}, {"$set": changes})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize(await get_or_404(product_id))


@app.post("/api/inventory/products/{product_id}/adjust")
async def adjust_stock(product_id: str, body: StockAdjust, user: str = Depends(require_user)):
    """Atomically change stock. Taking out more than is available fails with 409,
    so two orders can never oversell the same item."""
    oid = to_object_id(product_id)
    query = {"_id": oid}
    if body.delta < 0:
        query["quantity"] = {"$gte": -body.delta}
    result = await db.products.update_one(query, {"$inc": {"quantity": body.delta}})
    if result.matched_count == 0:
        await get_or_404(product_id)  # 404 if it doesn't exist at all
        raise HTTPException(status_code=409, detail="Insufficient stock")
    return serialize(await get_or_404(product_id))


@app.delete("/api/inventory/products/{product_id}", status_code=204)
async def delete_product(product_id: str, user: str = Depends(require_user)):
    result = await db.products.delete_one({"_id": to_object_id(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
