"""Lightweight FastAPI fixture target for Docker and CI E2E smoke runs."""

from fastapi import FastAPI

app = FastAPI(title="Recon Demo Target", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/items")
def list_items() -> dict[str, list[dict[str, object]]]:
    """Sample list endpoint for OpenAPI discovery."""
    return {"items": [{"id": 1, "name": "sample"}]}
