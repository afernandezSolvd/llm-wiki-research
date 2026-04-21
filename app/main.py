from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.audit import AuditMiddleware
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.router import api_router
from app.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="LLM Wiki",
    description="Enterprise-grade LLM-maintained knowledge base",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (configure origins per environment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
