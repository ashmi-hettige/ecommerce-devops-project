"""
Auth Service (microservice 1 of 2)
----------------------------------
Responsibility: check a username/password against MongoDB and issue a JWT.
It knows nothing about products. The inventory-service trusts the tokens
this service signs, because both share the same JWT_SECRET.

All settings come from environment variables so the same code runs on a
laptop, in Docker and in Kubernetes (where the values come from a
ConfigMap / Secret).
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

# ---------- Configuration (12-factor: read from the environment) ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "inventory_db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-before-deploying!!")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


class UserLogin(BaseModel):
    username: str
    password: str


# ---------- Startup: seed the admin user once ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not await db.users.find_one({"username": ADMIN_USERNAME}):
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt())
        await db.users.insert_one({"username": ADMIN_USERNAME, "password": hashed})
    yield


app = FastAPI(title="Auth Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # explicit list; "*" + credentials is rejected by browsers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exposes GET /metrics for Prometheus (request count, latency, status codes)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


# ---------- Routes ----------
@app.get("/health")
async def health():
    """Used by Kubernetes liveness/readiness probes."""
    await db.command("ping")
    return {"status": "ok", "service": "auth"}


@app.post("/api/auth/login")
async def login(user: UserLogin):
    db_user = await db.users.find_one({"username": user.username})
    if not db_user or not bcrypt.checkpw(user.password.encode("utf-8"), db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    token = jwt.encode({"sub": user.username, "exp": expires}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}
