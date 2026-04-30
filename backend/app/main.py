from contextlib import asynccontextmanager
import json
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.models.database import init_db
from app.utils.logging_config import setup_logging, get_logger
from app.api.models import router as models_router
from app.api.knowledge_bases import router as kb_router
from app.api.documents import router as documents_router
from app.api.compile import router as compile_router
from app.api.graph import router as graph_router
from app.api.chat import router as chat_router
from app.api.wiki import router as wiki_router

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(log_level=getattr(settings, "log_level", "INFO"))
    logger.info("SuperDeepAnalyze starting up")
    init_db()
    _recover_interrupted_compilations()
    logger.info("Database initialized")
    yield
    logger.info("SuperDeepAnalyze shutting down")


def _recover_interrupted_compilations():
    """Mark any 'processing' compilations from previous server session as 'failed'."""
    from app.models.database import get_connection

    conn = get_connection()
    try:
        cursor = conn.execute("SELECT id, kb_id FROM compile_queue WHERE status = 'processing'")
        interrupted = cursor.fetchall()
        for row in interrupted:
            conn.execute(
                "UPDATE compile_queue SET status = 'failed', error = '服务器重启中断', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
            conn.execute(
                "UPDATE knowledge_bases SET compile_status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["kb_id"],),
            )
            logger.info("Recovered interrupted compilation %s for KB %s", row["id"], row["kb_id"])
        conn.commit()
    except Exception as e:
        logger.error("Failed to recover compilations: %s", e)
        conn.rollback()
    finally:
        conn.close()


app = FastAPI(title="SuperDeepAnalyze", version="0.1.0", lifespan=lifespan)

app.include_router(models_router)
app.include_router(kb_router)
app.include_router(documents_router)
app.include_router(compile_router)
app.include_router(graph_router)
app.include_router(chat_router)
app.include_router(wiki_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://localhost:5173", "https://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Utf8Middleware(BaseHTTPMiddleware):
    """Ensure all responses use UTF-8 encoding for proper Chinese character support."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.media_type and "json" in response.media_type:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response


app.add_middleware(Utf8Middleware)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_logger("app.exception", path=request.url.path, method=request.method)
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())

    if "api/" in request.url.path:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
            media_type="application/json; charset=utf-8",
        )
    raise exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
