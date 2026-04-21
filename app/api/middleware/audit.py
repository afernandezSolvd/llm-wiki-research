"""Audit log middleware — writes an AuditLog row for mutating requests."""
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method not in AUDITED_METHODS:
            return response

        # Fire-and-forget audit log write
        try:
            user_id = _extract_user_id(request)
            workspace_id = _extract_workspace_id(request)

            if user_id:
                import asyncio
                asyncio.create_task(
                    _write_audit_log(
                        user_id=user_id,
                        workspace_id=workspace_id,
                        action=f"{request.method.lower()}.{request.url.path.strip('/').replace('/', '.')}",
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        status_code=response.status_code,
                    )
                )
        except Exception:
            pass  # Audit failures must not break the request

        return response


async def _write_audit_log(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    action: str,
    ip_address: str | None,
    user_agent: str | None,
    status_code: int,
):
    from app.core.db import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    async with AsyncSessionLocal() as db:
        db.add(AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            new_value={"status_code": status_code},
            created_at=datetime.now(UTC).isoformat(),
        ))
        await db.commit()


def _extract_user_id(request: Request) -> uuid.UUID | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from app.auth.jwt import decode_token
        return decode_token(auth[7:])
    except Exception:
        return None


def _extract_workspace_id(request: Request) -> uuid.UUID | None:
    path_parts = request.url.path.split("/")
    for i, part in enumerate(path_parts):
        if part == "workspaces" and i + 1 < len(path_parts):
            try:
                return uuid.UUID(path_parts[i + 1])
            except ValueError:
                pass
    return None
