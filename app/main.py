"""FastAPI application entrypoint for the Internal AI Knowledge Platform."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, gateway, health, query
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(
    title="Internal AI Knowledge Platform",
    description=(
        "A RAG backend for internal developers: upload documents/code, run "
        "semantic search, and access LLMs through a centralized AI gateway."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(gateway.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "service": "Internal AI Knowledge Platform",
        "version": app.version,
        "docs": "/docs",
    }
