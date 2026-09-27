"""
Inventory Service (microservice 2 of 2)
---------------------------------------
Responsibility: product CRUD in MongoDB. Every /api/inventory route
requires a valid JWT issued by the auth-service (shared JWT_SECRET).
"""
import os

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
    quantity: int = Field(ge=0)


class QuantityUpdate(BaseModel):
    quantity: int = Field(ge=0)


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
    return {"id": str(doc["_id"]), "name": doc["name"], "quantity": doc["quantity"]}


# ---------- Routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "inventory"}


@app.get("/api/inventory/products")
async def list_products(user: str = Depends(require_user)):
    docs = await db.products.find({}).to_list(1000)
    return [serialize(d) for d in docs]


@app.post("/api/inventory/products", status_code=201)
async def add_product(product: Product, user: str = Depends(require_user)):
    result = await db.products.insert_one(product.model_dump())
    return {"id": str(result.inserted_id), **product.model_dump()}


@app.put("/api/inventory/products/{product_id}")
async def update_quantity(product_id: str, body: QuantityUpdate, user: str = Depends(require_user)):
    result = await db.products.update_one(
        {"_id": to_object_id(product_id)}, {"$set": {"quantity": body.quantity}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"id": product_id, "quantity": body.quantity}


@app.delete("/api/inventory/products/{product_id}", status_code=204)
async def delete_product(product_id: str, user: str = Depends(require_user)):
    result = await db.products.delete_one({"_id": to_object_id(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
