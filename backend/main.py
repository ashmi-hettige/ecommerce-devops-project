from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone

app = FastAPI()

# Allow the frontend to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tier 3: In-House Database Connectivity (Using local MongoDB)
MONGO_URL = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URL)
db = client.inventory_db
SECRET_KEY = "devops_a_plus_secret_key"

class UserLogin(BaseModel):
    username: str
    password: str

class Product(BaseModel):
    name: str
    quantity: int

# Automatically create an admin user on server startup 
@app.on_event("startup")
async def setup_database():
    user = await db.users.find_one({"username": "admin"})
    if not user:
        hashed_pw = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        await db.users.insert_one({"username": "admin", "password": hashed_pw})

# Login Route (Generates Secure JWT Token)
@app.post("/login")
async def login(user: UserLogin):
    db_user = await db.users.find_one({"username": user.username})
    if not db_user or not bcrypt.checkpw(user.password.encode('utf-8'), db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = jwt.encode(
        {"sub": user.username, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, 
        SECRET_KEY, algorithm="HS256"
    )
    return {"access_token": token}

@app.get("/inventory")
async def get_inventory():
    return await db.products.find({}, {"_id": 0}).to_list(100)

@app.post("/inventory")
async def add_product(product: Product):
    await db.products.insert_one(product.model_dump())
    return {"message": "Product added locally!"}