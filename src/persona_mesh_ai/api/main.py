"""FastAPI entry point for Persona Mesh AI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from persona_mesh_ai.core.main import (
    GenerateRequest,
    generate_post,
    list_personas,
    stream_post,
)

logger = logging.getLogger("persona_mesh_ai.api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Persona Mesh AI API",
    description="A platform for orchestrating configurable AI agents.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "Persona Mesh AI", "status": "running", "version": "0.1.0"}


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