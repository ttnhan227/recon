from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Recon Demo Target Application",
    description="A deliberately vulnerable and defect-laden demo application for Recon QA verification.",
    version="1.0.0",
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


class UserCreateRequest(BaseModel):
    name: str = Field(description="User full name", default="Alice")
    email: str = Field(description="User email address", default="alice@example.com")
    password: str = Field(description="User password", default="Secret123!")


class OrderItem(BaseModel):
    sku: str = Field(default="ITEM-001")
    quantity: int = Field(default=1)


class OrderCreateRequest(BaseModel):
    item_id: str = Field(default="ITEM-100")
    quantity: int = Field(default=1)
    currency: str | None = Field(
        default=None, description="Optional currency in schema, but causes 500 when omitted"
    )


# 1. Health check
@app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "recon-demo-app", "version": "1.0.0"}


# 2. User Creation with Broken Email Validation
@app.post("/api/users", status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(user: UserCreateRequest):
    # Intentional bug: Flawed regex rejects valid standard emails with numbers or tags
    if re.search(r"[0-9\+]", user.email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid email address format (rejected character): {user.email}",
        )
    return {"id": "usr_99812", "name": user.name, "email": user.email, "status": "active"}


# 3. Order Processing with 500 NullReferenceException
@app.post("/api/orders", status_code=status.HTTP_201_CREATED, tags=["Orders"])
async def create_order(order: OrderCreateRequest):
    # Intentional bug: Server assumes currency is always present, throws 500 when omitted
    if not order.currency:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NullReferenceException: Object reference not set to an instance of an object at PaymentGateway.ValidateCurrency(payment.currency)",
        )
    return {
        "order_id": "ord_5521",
        "item_id": order.item_id,
        "quantity": order.quantity,
        "currency": order.currency.upper(),
        "total_amount": 99.95,
    }


# 4. Security / Authorization Flaw
@app.get("/api/admin/secrets", tags=["Admin"])
async def get_admin_secrets():
    # Intentional bug: No auth verification! Exposed to anonymous users
    return {
        "database_master_password": "super_secret_production_password_2026",
        "jwt_private_key": "-----BEGIN RSA PRIVATE KEY-----MIIEpAIBAAKCAQEA...",
        "environment": "production",
    }


# 5. Slow Analytics Endpoint (Latency Issue)
@app.get("/api/slow-analytics", tags=["Analytics"])
async def slow_analytics():
    # Intentional bug: Artificially delayed execution
    await asyncio.sleep(2.0)
    return {"metric": "user_engagement", "value": 98.4, "computation_time_seconds": 2.0}


# 6. Inventory Reservation
@app.post("/api/inventory/reserve", tags=["Inventory"])
async def reserve_inventory(item: OrderItem):
    if item.quantity > 50:
        raise HTTPException(status_code=400, detail="Insufficient inventory available")
    return {"status": "reserved", "sku": item.sku, "quantity": item.quantity}


# 7. Web Pages
@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
async def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Recon Demo App</h1>")


@app.get("/dashboard", response_class=HTMLResponse, tags=["Web UI"])
async def dashboard_page():
    dash_file = STATIC_DIR / "dashboard.html"
    if dash_file.exists():
        return HTMLResponse(content=dash_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard</h1>")
