from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    graph,
    ingest,
    lint,
    public,
    query,
    schema,
    sources,
    status,
    wiki,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(sources.router)
api_router.include_router(wiki.router)
api_router.include_router(ingest.router)
api_router.include_router(query.router)
api_router.include_router(lint.router)
api_router.include_router(schema.router)
api_router.include_router(graph.router)
api_router.include_router(admin.router)
api_router.include_router(status.router)
api_router.include_router(public.router)
