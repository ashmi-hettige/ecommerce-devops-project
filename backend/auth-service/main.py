"""
Auth Service (microservice 1 of 3)
----------------------------------
Responsibility: user accounts, roles, and secure login.

* Passwords are hashed with bcrypt (never stored in plain text).
* After MAX_FAILED_ATTEMPTS wrong passwords an account is locked for LOCKOUT_MINUTES.
* New passwords must pass a strength policy.
* Users created or reset by an admin must change their password at next login.
* Anyone can REGISTER, but the account stays "pending" (no role, cannot sign in)
  until an admin approves it and assigns a role.
* The JWT this service signs carries the user's ROLE and PERMISSIONS.
  The other services only check permissions in the token, so the
  role -> permission mapping below is the single source of truth.
"""
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# ---------- Configuration (12-factor: read from the environment) ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "inventory_db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-before-deploying!!")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
# In production set ADMIN_PASSWORD through an environment variable / Kubernetes Secret.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Adm1n@Stock#2026")
LEGACY_WEAK_PASSWORDS = ["admin123"]  # old defaults that must never keep working
SEED_DEMO_USERS = os.getenv("SEED_DEMO_USERS", "true").lower() == "true"
MAX_FAILED_ATTEMPTS = int(os.getenv("MAX_FAILED_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ---------- Role-based access control ----------
ROLES = {
    "admin": {
        "label": "Admin",
        "description": "Full access, user management and settings.",
        "permissions": [
            "products:read", "products:write", "products:price",
            "stock:adjust", "stock:receive", "stock:count",
            "orders:read", "orders:create", "orders:delete", "orders:fulfil", "orders:return",
            "reports:read", "users:manage",
        ],
    },
    "inventory_manager": {
        "label": "Inventory manager",
        "description": "Products, prices, stock, purchasing (receiving) and reports.",
        "permissions": [
            "products:read", "products:write", "products:price",
            "stock:adjust", "stock:receive", "stock:count",
            "orders:read", "reports:read",
        ],
    },
    "warehouse": {
        "label": "Warehouse staff",
        "description": "Receiving, picking, packing and stock counts. Cannot change prices.",
        "permissions": [
            "products:read", "stock:receive", "stock:count",
            "orders:read", "orders:fulfil",
        ],
    },
    "sales": {
        "label": "Sales / customer service",
        "description": "Creates and cancels orders and handles returns.",
        "permissions": [
            "products:read", "orders:read", "orders:create", "orders:delete", "orders:return",
        ],
    },
}
RoleName = Literal["admin", "inventory_manager", "warehouse", "sales"]

# Prometheus: security metrics for Grafana
LOGINS = Counter("auth_login_total", "Login attempts by result", ["result"])

# A real bcrypt hash, used so a login for an unknown user takes as long as a
# wrong password (stops attackers discovering usernames by timing).
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt())


# ---------- Helpers ----------
def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Mongo returns naive UTC datetimes; make them timezone-aware."""
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def hash_password(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())


def password_problems(pw: str, username: str = "") -> list[str]:
    problems = []
    if len(pw) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Za-z]", pw):
        problems.append("a letter")
    if not re.search(r"\d", pw):
        problems.append("a number")
    if username and pw.lower() == username.lower():
        problems.append("must not be the same as the username")
    return problems


def check_policy(pw: str, username: str = ""):
    problems = password_problems(pw, username)
    if problems:
        raise HTTPException(status_code=422, detail="Password needs " + ", ".join(problems) + ".")


def issue_token(user: dict) -> str:
    role = user.get("role", "admin")
    payload = {
        "sub": user["username"],
        "name": user.get("full_name") or user["username"],
        "role": role,
        "perms": ROLES[role]["permissions"],
        "pwd_change": bool(user.get("must_change_password")),
        "iat": now(),
        "exp": now() + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def public_user(u: dict) -> dict:
    locked_until = aware(u.get("locked_until"))
    return {
        "username": u["username"],
        "full_name": u.get("full_name", ""),
        "role": u.get("role", "admin"),
        "pending": u.get("role", "admin") is None,
        "active": u.get("active", True),
        "locked": bool(locked_until and locked_until > now()),
        "must_change_password": bool(u.get("must_change_password")),
        "last_login": aware(u["last_login"]).isoformat() if u.get("last_login") else None,
    }


# ---------- Auth dependencies ----------
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


# ---------- Startup: seed users ----------
async def seed_user(username, password, role, full_name, force_role=False):
    existing = await db.users.find_one({"username": username})
    if not existing:
        await db.users.insert_one({
            "username": username, "password": hash_password(password), "role": role,
            "full_name": full_name, "active": True, "must_change_password": False,
            "failed_attempts": 0, "created_at": now(),
        })
    elif force_role and "role" not in existing:
        # Upgrade users created before roles existed
        await db.users.update_one({"_id": existing["_id"]},
                                  {"$set": {"role": role, "active": True, "full_name": full_name}})


async def upgrade_weak_admin_password():
    """If the admin account still uses an old weak default password,
    replace it with ADMIN_PASSWORD (which must pass the password policy)."""
    admin = await db.users.find_one({"username": ADMIN_USERNAME})
    if not admin or password_problems(ADMIN_PASSWORD, ADMIN_USERNAME):
        return
    for weak in LEGACY_WEAK_PASSWORDS:
        if bcrypt.checkpw(weak.encode("utf-8"), admin["password"]):
            await db.users.update_one({"_id": admin["_id"]}, {"$set": {"password": hash_password(ADMIN_PASSWORD)}})
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_user(ADMIN_USERNAME, ADMIN_PASSWORD, "admin", "Administrator", force_role=True)
    await upgrade_weak_admin_password()
    if SEED_DEMO_USERS:
        await seed_user("manager", "Manager@123", "inventory_manager", "Inventory Manager")
        await seed_user("warehouse", "Warehouse@123", "warehouse", "Warehouse Staff")
        await seed_user("sales", "Sales@123", "sales", "Sales Agent")
    yield


app = FastAPI(title="Auth Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


# ---------- Models ----------
class UserLogin(BaseModel):
    username: str
    password: str


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(default="", max_length=80)
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(default="", max_length=80)
    role: RoleName
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=80)
    role: Optional[RoleName] = None  # setting a role on a pending user approves them
    active: Optional[bool] = None


class ResetPassword(BaseModel):
    password: str


# ---------- Public routes ----------
@app.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "auth"}


@app.post("/api/auth/login")
async def login(body: UserLogin):
    user = await db.users.find_one({"username": body.username})

    if not user:
        bcrypt.checkpw(body.password.encode("utf-8"), _DUMMY_HASH)  # same timing as a real check
        LOGINS.labels("failure").inc()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    locked_until = aware(user.get("locked_until"))
    if locked_until and locked_until > now():
        minutes = int((locked_until - now()).total_seconds() // 60) + 1
        LOGINS.labels("locked").inc()
        raise HTTPException(status_code=423,
                            detail=f"Account locked after too many failed attempts. Try again in {minutes} min.")

    if not bcrypt.checkpw(body.password.encode("utf-8"), user["password"]):
        attempts = user.get("failed_attempts", 0) + 1
        update = {"failed_attempts": attempts}
        if attempts >= MAX_FAILED_ATTEMPTS:
            update = {"failed_attempts": 0, "locked_until": now() + timedelta(minutes=LOCKOUT_MINUTES)}
        await db.users.update_one({"_id": user["_id"]}, {"$set": update})
        LOGINS.labels("failure").inc()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.get("role", "admin") is None:
        LOGINS.labels("pending").inc()
        raise HTTPException(status_code=403, detail="Your account is waiting for an administrator to approve it.")

    if not user.get("active", True):
        LOGINS.labels("disabled").inc()
        raise HTTPException(status_code=403, detail="This account is disabled. Contact an administrator.")

    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"failed_attempts": 0, "locked_until": None, "last_login": now()}})
    LOGINS.labels("success").inc()
    return {"access_token": issue_token(user), "token_type": "bearer", "user": public_user(user)}


@app.post("/api/auth/register", status_code=201)
async def register(body: Registration):
    """Self-registration. The account gets NO role until an admin approves it,
    so registering never grants access by itself."""
    if await db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=409, detail="That username is already taken")
    check_policy(body.password, body.username)
    await db.users.insert_one({
        "username": body.username, "full_name": body.full_name, "role": None,
        "password": hash_password(body.password), "active": True,
        "must_change_password": False, "failed_attempts": 0,
        "created_at": now(), "created_by": "self-registration",
    })
    return {"message": "Account created. An administrator must approve it before you can sign in."}


@app.get("/api/auth/roles")
async def roles():
    return ROLES


# ---------- Signed-in user ----------
@app.get("/api/auth/me")
async def me(claims: dict = Depends(current_claims)):
    user = await db.users.find_one({"username": claims["sub"]})
    if not user or user.get("role", "admin") is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {**public_user(user), "permissions": ROLES[user.get("role", "admin")]["permissions"]}


@app.post("/api/auth/change-password")
async def change_password(body: ChangePassword, claims: dict = Depends(current_claims)):
    user = await db.users.find_one({"username": claims["sub"]})
    if not user or not bcrypt.checkpw(body.current_password.encode("utf-8"), user["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="New password must be different from the current one.")
    check_policy(body.new_password, user["username"])
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"password": hash_password(body.new_password),
                                        "must_change_password": False}})
    user["must_change_password"] = False
    return {"access_token": issue_token(user), "token_type": "bearer"}


# ---------- User administration (admin only) ----------
@app.get("/api/auth/users")
async def list_users(claims: dict = Depends(require("users:manage"))):
    users = await db.users.find({}).sort("username", 1).to_list(1000)
    return [public_user(u) for u in users]


@app.post("/api/auth/users", status_code=201)
async def create_user(body: NewUser, claims: dict = Depends(require("users:manage"))):
    if await db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=409, detail="That username is already taken")
    check_policy(body.password, body.username)
    doc = {
        "username": body.username, "full_name": body.full_name, "role": body.role,
        "password": hash_password(body.password), "active": True,
        "must_change_password": True,  # temporary password chosen by the admin
        "failed_attempts": 0, "created_at": now(), "created_by": claims["sub"],
    }
    await db.users.insert_one(doc)
    return public_user(doc)


async def active_admin_count() -> int:
    return await db.users.count_documents({"role": "admin", "active": {"$ne": False}})


@app.patch("/api/auth/users/{username}")
async def update_user(username: str, body: UserUpdate, claims: dict = Depends(require("users:manage"))):
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update")

    # Never leave the system without an active admin
    losing_admin = user.get("role", "admin") == "admin" and (
        changes.get("role", "admin") != "admin" or changes.get("active") is False)
    if losing_admin and username == claims["sub"]:
        raise HTTPException(status_code=409, detail="You can't remove your own admin access or disable yourself.")
    if losing_admin and await active_admin_count() <= 1:
        raise HTTPException(status_code=409, detail="There must be at least one active admin.")

    await db.users.update_one({"_id": user["_id"]}, {"$set": changes})
    return public_user({**user, **changes})


@app.post("/api/auth/users/{username}/reset-password")
async def reset_password(username: str, body: ResetPassword, claims: dict = Depends(require("users:manage"))):
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    check_policy(body.password, username)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {
        "password": hash_password(body.password), "must_change_password": True,
        "failed_attempts": 0, "locked_until": None,
    }})
    return {"message": f"Password reset. {username} must choose a new password at next login."}


@app.post("/api/auth/users/{username}/unlock")
async def unlock_user(username: str, claims: dict = Depends(require("users:manage"))):
    result = await db.users.update_one({"username": username},
                                       {"$set": {"failed_attempts": 0, "locked_until": None}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"{username} unlocked"}
