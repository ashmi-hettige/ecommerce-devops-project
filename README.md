# Inventory Management System

A microservice-based inventory and order management system, built as a DevOps project.
It has a Vue 3 web app in front of three FastAPI services that share a MongoDB database.
Each part has its own Dockerfile.

## Features

- **Inventory:** products with SKU, category and unit price, plus stock levels and low-stock alerts.
  Stock changes through deliveries (receive), stock counts and manual adjustments.
- **Orders:** orders reserve stock as soon as they're created. Each order then goes through
  *pending → picked → packed → shipped*, and shipped orders can be returned.
- **Insights dashboard:** key figures, items that need restocking, orders by status, top products
  by stock value, recent orders, and a full log of stock movements.
- **Users and roles:** login with JWT, role-based permissions, admin approval for new sign-ups,
  account lockout after repeated failed logins, and password rules.
- **Monitoring:** every service exposes `/health` and Prometheus metrics at `/metrics`.

## Architecture

```
                 ┌──────────────────────────────────────────┐
  Browser ──────►│  frontend  (Vue 3, served by Nginx :80)  │
                 └──────┬───────────────┬───────────────┬───┘
                /api/auth        /api/inventory     /api/orders
                        ▼               ▼               ▼
                 auth-service   inventory-service   order-service
                    :8001            :8002              :8003
                        └───────────────┼───────────────┘
                                        ▼
                                     MongoDB
```

- The browser only talks to the frontend. Nginx forwards each `/api/...` path to the right
  service, so there are no hard-coded backend URLs and no CORS problems.
- `auth-service` signs JWTs that include the user's role and permissions. The other services
  verify these tokens with the same `JWT_SECRET` and check permissions on every request.
  The frontend only hides what a user can't use.
- `order-service` calls `inventory-service` to reserve and release stock.

## Repository layout

| Path | What it is |
|---|---|
| `frontend/` | Vue 3 + Vite app, `Dockerfile`, `nginx.conf` |
| `backend/auth-service/` | Login, registration, users, roles (port 8001) |
| `backend/inventory-service/` | Products, stock and stock movements (port 8002) |
| `backend/order-service/` | Orders, fulfilment and returns (port 8003) |

Branches: `frontend` and `backend` are where each part is developed, and `main` combines both.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3, Vite, Axios, Nginx |
| Backend | Python 3.12, FastAPI, Uvicorn, Motor (async MongoDB), PyJWT, bcrypt |
| Database | MongoDB |
| Monitoring | prometheus-fastapi-instrumentator |
| Testing | pytest, httpx, mongomock-motor |
| Containers | Docker |

## Roles and permissions

| Permission | Admin | Inventory manager | Warehouse staff | Sales |
|---|:-:|:-:|:-:|:-:|
| View products and stock | ✓ | ✓ | ✓ | ✓ |
| Create, edit and delete products | ✓ | ✓ | | |
| Set and change prices | ✓ | ✓ | | |
| Adjust stock (+/−) | ✓ | ✓ | | |
| Receive deliveries | ✓ | ✓ | ✓ | |
| Record stock counts | ✓ | ✓ | ✓ | |
| View orders | ✓ | ✓ | ✓ | ✓ |
| Create and cancel orders | ✓ | | | ✓ |
| Pick, pack and ship orders | ✓ | | ✓ | |
| Process returns | ✓ | | | ✓ |
| View reports | ✓ | ✓ | | |
| Manage users and roles | ✓ | | | |

## Running locally (development)

You'll need Node.js 22+, Python 3.12+ and MongoDB running on `localhost:27017`.

**1. Backend:** do this once for each of the three services, in its own terminal:

```bash
cd backend/auth-service          # then inventory-service, then order-service
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then edit .env and set your own values
uvicorn main:app --port 8001     # inventory: 8002, order: 8003
```

`JWT_SECRET` must be the same in all three `.env` files.

**2. Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server forwards `/api/...` requests to the three services.

**3. Sign in:** log in as `admin` with the `ADMIN_PASSWORD` from `auth-service/.env`. When
`SEED_DEMO_USERS=true`, the demo accounts `manager`, `warehouse` and `sales` are also created
(see `auth-service/main.py`). Set `SEED_DEMO_USERS=false` outside development.

## Docker

Each part builds into its own image:

```bash
docker build -t inventory-frontend   ./frontend
docker build -t auth-service         ./backend/auth-service
docker build -t inventory-service    ./backend/inventory-service
docker build -t order-service        ./backend/order-service
```

When you run them together (for example with Docker Compose), keep these points in mind:

- Name the containers `auth-service`, `inventory-service` and `order-service`, because
  `frontend/nginx.conf` forwards requests to those hostnames.
- Point every service at the database with `MONGO_URL=mongodb://<mongo-host>:27017`.
- Set `INVENTORY_URL=http://inventory-service:8002` on `order-service`.
- Pass `JWT_SECRET` (the same value everywhere) and `ADMIN_PASSWORD` as environment variables.
  The `.dockerignore` files keep `.env` out of the images.
- Publish only the frontend's port 80 (for example `-p 8080:80`).

## Configuration

Each service reads its settings from environment variables. `.env.example` in each service
folder lists them all.

| Variable | Used by | Purpose |
|---|---|---|
| `MONGO_URL`, `DB_NAME` | all | MongoDB connection |
| `JWT_SECRET` | all | Signs and verifies login tokens; must match across services |
| `CORS_ORIGINS` | all | Allowed browser origins (only needed without the proxy) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | auth | The initial admin account |
| `TOKEN_EXPIRE_MINUTES` | auth | How long a login lasts |
| `SEED_DEMO_USERS` | auth | Create demo accounts (development only) |
| `MAX_FAILED_ATTEMPTS`, `LOCKOUT_MINUTES` | auth | Account lockout policy |
| `INVENTORY_URL` | order | Where `order-service` reaches `inventory-service` |

Never commit a real `.env` file.

## Tests

Each service has its own pytest suite, which uses an in-memory MongoDB mock:

```bash
cd backend/auth-service          # or inventory-service / order-service
pip install -r requirements-dev.txt
pytest
```

## Health and metrics

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check for each service |
| `GET /metrics` | Prometheus metrics: request counts, latency, and login outcomes on `auth-service` |

## Author

H.A. Imanda ([@ashmi-hettige](https://github.com/ashmi-hettige))
