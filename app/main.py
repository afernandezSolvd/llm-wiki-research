from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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


# ── MCP Streamable HTTP transport ────────────────────────────────────────────
# Guard: validate bearer token for every request under /mcp before the
# Starlette sub-app handles it, since mounted apps bypass FastAPI dependencies.
@app.middleware("http")
async def _mcp_auth_guard(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        try:
            from app.auth.jwt import decode_token
            decode_token(auth[7:])
        except Exception:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
    return await call_next(request)


from app.mcp.server import get_http_app as _get_mcp_http_app  # noqa: E402

app.mount("/mcp", _get_mcp_http_app())
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}


@app.get("/status", include_in_schema=False)
async def status_dashboard():
    return FileResponse("app/static/status.html")
