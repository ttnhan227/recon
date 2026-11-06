from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

test_app = FastAPI(
    title="Recon Internal Test Target",
    description="Internal test target for unit and integration testing of Recon QA runner.",
    version="1.0.0",
)


class UserCreate(BaseModel):
    name: str = Field(default="Alice")
    email: str = Field(default="alice@example.com")
    password: str = Field(default="Secret123!")


class OrderCreate(BaseModel):
    item_id: str = Field(default="ITEM-100")
    quantity: int = Field(default=1)
    currency: str | None = Field(default=None)


class InventoryReserve(BaseModel):
    sku: str = Field(default="ITEM-001")
    quantity: int = Field(default=1)


@test_app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "recon-qa", "version": "1.0.0"}


@test_app.post("/api/users", status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(user: UserCreate):
    if re.search(r"[0-9\+]", user.email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid email format: {user.email}",
        )
    return {"id": "usr_123", "name": user.name, "email": user.email}


@test_app.post("/api/orders", status_code=status.HTTP_201_CREATED, tags=["Orders"])
async def create_order(order: OrderCreate):
    if not order.currency:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NullReferenceException: currency is required",
        )
    return {"order_id": "ord_100", "currency": order.currency}


@test_app.get("/api/admin/secrets", tags=["Admin"])
async def get_admin_secrets():
    return {"environment": "test", "key": "test_secret"}


@test_app.post("/api/inventory/reserve", tags=["Inventory"])
async def reserve_inventory(item: InventoryReserve):
    if item.quantity > 50:
        raise HTTPException(status_code=400, detail="Insufficient inventory")
    return {"status": "reserved", "sku": item.sku, "quantity": item.quantity}
