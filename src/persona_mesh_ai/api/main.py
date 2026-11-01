"""FastAPI entry point for Persona Mesh AI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse


from pathlib import Path
from fastapi.staticfiles import StaticFiles


from persona_mesh_ai.core.main import (
    GenerateRequest,
    generate_post,
    list_personas,
    stream_post,
    DevToPublishRequest,
    list_devto_accounts,
    post_to_dev_to,
)
from persona_mesh_ai.api.user_routes import router as user_router
from persona_mesh_ai.api.user_store import init_db


STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

from persona_mesh_ai.core.main import (
    GenerateRequest,
    generate_post,
    list_personas,
    stream_post,
)

logger = logging.getLogger("persona_mesh_ai.api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="Persona Mesh AI API",
    description="A platform for orchestrating configurable AI agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(user_router)

app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/user", include_in_schema=False)
@app.get("/users", include_in_schema=False)
async def users_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "users.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/v1/personas")
async def get_personas() -> list[dict[str, Any]]:
    """List available writing personas (their ids can be passed as persona_id)."""
    return list_personas()


@app.post("/api/v1/chat")
async def chat(request: GenerateRequest) -> dict[str, Any]:
    try:
        result = generate_post(request)
    except ValueError as exc:
        logger.warning("Generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during generation")
        raise HTTPException(status_code=500, detail="Internal generation error") from exc

    if "error" in result:
        raise HTTPException(status_code=422, detail=result)

    return result


@app.post("/api/v1/chat/stream")
def chat_stream(request: GenerateRequest) -> StreamingResponse:
    def _gen():
        try:
            yield from stream_post(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Streaming error")
            yield f"\n[stream error: {exc}]"

    return StreamingResponse(_gen(), media_type="text/plain")



@app.get("/api/v1/devto/accounts")
async def devto_accounts() -> list[dict[str, str]]:
    """List configured Dev.to accounts (ids only)."""
    return list_devto_accounts()


@app.post("/api/v1/devto/publish")
async def devto_publish(request: DevToPublishRequest) -> dict[str, Any]:
    if not request.publish:
        return {
            "status": "skipped",
            "account_id": request.account_id,
            "reason": "Publishing was not requested (publish=false).",
            "http_status": None,
            "article_url": None,
            "raw": None,
        }
    try:
        return post_to_dev_to(
            request.post,
            account_id=request.account_id,
            publish=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Dev.to publish failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
