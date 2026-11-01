"""FastAPI entry point for Persona Mesh AI."""

from __future__ import annotations

import json
import logging
import random
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from persona_mesh_ai.api import (
    activity_store,
    generation_store,
    publishing_store,
    user_store,
)
from persona_mesh_ai.api.user_routes import router as user_router
from persona_mesh_ai.core.main import (
    DevToPublishRequest,
    GenerateRequest,
    _has_minimum_detail,
    generate_post,
    list_devto_accounts,
    parse_response,
    post_to_dev_to,
    stream_post,
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("persona_mesh_ai.api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    user_store.init_db()
    generation_store.init_db()
    activity_store.init_db()
    publishing_store.init_db()
    publishing_store.sync_environment_accounts(list_devto_accounts())
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
    allow_origins=["*"],  # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/post", include_in_schema=False)
async def post_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/user", include_in_schema=False)
@app.get("/users", include_in_schema=False)
async def users_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "users.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/v1/platforms")
def get_platforms() -> list[dict[str, str]]:
    try:
        return generation_store.list_platforms()
    except sqlite3.Error as exc:
        logger.exception("Could not load platforms")
        raise HTTPException(status_code=503, detail="Could not load platforms") from exc


@app.get("/api/v1/personas")
def get_personas() -> list[dict[str, Any]]:
    """List personas persisted through user management."""
    try:
        users = _load_personas_from_database()
    except sqlite3.Error as exc:
        logger.exception("Could not load personas")
        raise HTTPException(status_code=503, detail="Could not load personas") from exc
    return [
        {
            key: user[key]
            for key in (
                "id",
                "name",
                "role",
                "description",
                "relationship",
                "personality",
            )
        }
        for user in users
    ]


def _load_personas_from_database() -> list[dict[str, Any]]:
    required_fields = ("name", "role", "description", "relationship", "personality")
    return [
        user
        for user in user_store.list_users()
        if all(
            isinstance(user.get(field), str) and user[field].strip()
            for field in required_fields
        )
    ]


def _resolve_generation_persona(
    request: GenerateRequest,
) -> tuple[GenerateRequest, list[dict[str, Any]], dict[str, Any]]:
    try:
        platforms = generation_store.list_platforms()
        persona_registry = _load_personas_from_database()
    except sqlite3.Error as exc:
        logger.exception("Could not load a writing persona")
        raise HTTPException(
            status_code=503, detail="Could not load personas from the database"
        ) from exc

    if request.platform not in {platform["id"] for platform in platforms}:
        raise HTTPException(
            status_code=422, detail="Selected platform is not available"
        )

    if not persona_registry:
        raise HTTPException(
            status_code=409,
            detail="No personas are saved. Add a persona from the Users page first.",
        )

    if request.persona_id:
        selected = next(
            (
                persona
                for persona in persona_registry
                if persona["id"] == request.persona_id
            ),
            None,
        )
        if selected is None:
            raise HTTPException(
                status_code=422, detail="Selected persona was not found"
            )
    else:
        selected = random.choice(persona_registry)

    effective_request = request.model_copy(update={"persona_id": selected["id"]})
    return effective_request, persona_registry, selected


@app.post("/api/v1/chat")
async def chat(request: GenerateRequest) -> dict[str, Any]:
    effective_request, persona_registry, selected_persona = _resolve_generation_persona(
        request
    )
    try:
        result = generate_post(effective_request, persona_registry)
    except ValueError as exc:
        logger.warning("Generation failed: %s", exc)
        try:
            activity_store.log_event(
                "generation_failed",
                "generation",
                "Post generation failed",
                actor_id=effective_request.persona_id,
                actor_name=selected_persona.get("name"),
                details={"platform": effective_request.platform, "error": str(exc)},
            )
        except sqlite3.Error:
            logger.exception("Generation failure activity could not be recorded")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error during generation")
        try:
            activity_store.log_event(
                "generation_failed",
                "generation",
                "Post generation failed unexpectedly",
                actor_id=effective_request.persona_id,
                details={"platform": effective_request.platform, "error": str(exc)},
            )
        except sqlite3.Error:
            logger.exception("Generation failure activity could not be recorded")
        raise HTTPException(
            status_code=500, detail="Internal generation error"
        ) from exc

    if "error" in result:
        try:
            activity_store.log_event(
                "generation_rejected",
                "generation",
                "Generation returned insufficient detail",
                actor_id=effective_request.persona_id,
                actor_name=selected_persona.get("name"),
                details={
                    "platform": effective_request.platform,
                    "error": result.get("error"),
                    "reason": result.get("reason"),
                },
            )
        except sqlite3.Error:
            logger.exception("Generation rejection activity could not be recorded")
        raise HTTPException(status_code=422, detail=result)

    result["target_name"] = effective_request.target_person.name
    try:
        generation_id = generation_store.save_generation(
            effective_request.model_dump(),
            result,
            raw_text=json.dumps(result, ensure_ascii=False, default=str),
        )
        result["generation_id"] = generation_id
        result["generation_saved"] = True
        try:
            activity_store.log_event(
                "generation_completed",
                "generation",
                f"Generated a post: {result.get('title') or 'Untitled'}",
                entity_id=generation_id,
                actor_id=str(result.get("writing_user_id") or "") or None,
                actor_name=result.get("writing_user"),
                details={
                    "platform": result.get("platform"),
                    "target_name": result.get("target_name"),
                    "word_count": result.get("word_count"),
                },
            )
        except sqlite3.Error:
            logger.exception("Generation activity could not be recorded")
    except sqlite3.Error:
        logger.exception("Generated content could not be saved")
        result["generation_saved"] = False
        result["save_warning"] = (
            "The post was generated but could not be saved to the database."
        )

    return result


@app.post("/api/v1/chat/stream")
def chat_stream(request: GenerateRequest) -> StreamingResponse:
    effective_request, persona_registry, writing_user = _resolve_generation_persona(
        request
    )
    enough_detail, reason = _has_minimum_detail(effective_request)
    if not enough_detail:
        raise HTTPException(
            status_code=422,
            detail={"error": "insufficient_target_detail", "reason": reason},
        )

    def _gen():
        chunks: list[str] = []
        completed = False
        try:
            for chunk in stream_post(effective_request, persona_registry):
                chunks.append(chunk)
                yield chunk
            completed = True
        except Exception as exc:
            logger.exception("Streaming error")
            yield f"\n[stream error: {exc}]"
        finally:
            raw_text = "".join(chunks)
            if raw_text and not raw_text.startswith("[error:"):
                try:
                    result = parse_response(raw_text, effective_request)
                    result["writing_user"] = writing_user["name"]
                    result["writing_user_id"] = writing_user["id"]
                    result["target_name"] = effective_request.target_person.name
                    generation_id = generation_store.save_generation(
                        effective_request.model_dump(),
                        result,
                        raw_text=raw_text,
                        generation_mode="stream",
                        status="completed" if completed else "partial",
                    )
                    activity_store.log_event(
                        "generation_completed" if completed else "generation_partial",
                        "generation",
                        f"Streamed a post: {result.get('title') or 'Untitled'}",
                        entity_id=generation_id,
                        actor_id=writing_user.get("id"),
                        actor_name=writing_user.get("name"),
                        details={
                            "platform": result.get("platform"),
                            "target_name": result.get("target_name"),
                            "word_count": result.get("word_count"),
                        },
                    )
                except Exception:
                    logger.exception("Streamed content could not be saved")

    return StreamingResponse(_gen(), media_type="text/plain")


@app.get("/api/v1/generations")
def list_generations(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        return generation_store.list_generations(limit=limit, offset=offset)
    except sqlite3.Error as exc:
        logger.exception("Could not load generation history")
        raise HTTPException(
            status_code=503, detail="Could not load generation history"
        ) from exc


@app.get("/api/v1/generations/{generation_id}")
def get_generation(generation_id: int) -> dict[str, Any]:
    try:
        generation = generation_store.get_generation(generation_id)
    except sqlite3.Error as exc:
        logger.exception("Could not load generation %s", generation_id)
        raise HTTPException(
            status_code=503, detail="Could not load the saved generation"
        ) from exc
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    try:
        generation["publishing"] = activity_store.list_generation_publishing(
            generation_id
        )
    except sqlite3.Error as exc:
        logger.exception(
            "Could not load publishing state for generation %s", generation_id
        )
        raise HTTPException(
            status_code=503, detail="Could not load publishing state"
        ) from exc
    return generation


@app.get("/api/v1/dashboard")
def get_dashboard() -> dict[str, Any]:
    try:
        return activity_store.dashboard_summary()
    except sqlite3.Error as exc:
        logger.exception("Could not load dashboard data")
        raise HTTPException(
            status_code=503, detail="Could not load dashboard data"
        ) from exc


@app.get("/api/v1/activity")
def get_activity(limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    try:
        return activity_store.list_activity(limit)
    except sqlite3.Error as exc:
        logger.exception("Could not load activity")
        raise HTTPException(status_code=503, detail="Could not load activity") from exc


@app.get("/api/v1/publishing-history")
def get_publishing_history(
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict[str, Any]]:
    try:
        return activity_store.list_publishing_history(limit)
    except sqlite3.Error as exc:
        logger.exception("Could not load publishing history")
        raise HTTPException(
            status_code=503, detail="Could not load publishing history"
        ) from exc


@app.get("/api/v1/devto/accounts")
def devto_accounts() -> list[dict[str, Any]]:
    """List publishing account metadata persisted in SQLite."""
    try:
        return publishing_store.list_accounts()
    except sqlite3.Error as exc:
        logger.exception("Could not load publishing accounts")
        raise HTTPException(
            status_code=503, detail="Could not load publishing accounts"
        ) from exc


@app.post("/api/v1/devto/publish")
async def devto_publish(request: DevToPublishRequest) -> dict[str, Any]:
    account_ids = list(
        dict.fromkeys(
            request.account_ids
            if request.account_ids is not None
            else [request.account_id or "default"]
        )
    )
    if not account_ids:
        raise HTTPException(status_code=422, detail="Select at least one account")

    results: list[dict[str, Any]] = []
    for account_id in account_ids:
        try:
            account = publishing_store.get_account(account_id)
        except sqlite3.Error as exc:
            logger.exception("Could not load publishing account %s", account_id)
            raise HTTPException(
                status_code=503, detail="Could not load publishing accounts"
            ) from exc

        if account is None:
            results.append(
                {
                    "status": "error",
                    "account_id": account_id,
                    "reason": "Account was not found in the database.",
                    "http_status": None,
                    "article_url": None,
                    "raw": None,
                }
            )
        elif not account["configured"]:
            results.append(
                {
                    "status": "error",
                    "account_id": account_id,
                    "reason": "No API key is configured for this account.",
                    "http_status": None,
                    "article_url": None,
                    "raw": None,
                }
            )
        else:
            try:
                existing_draft = (
                    activity_store.find_latest_draft(request.generation_id, account_id)
                    if request.generation_id is not None
                    else None
                )
                results.append(
                    post_to_dev_to(
                        request.post,
                        account_id=account_id,
                        publish=request.publish,
                        api_key_override=account.get("api_key"),
                        existing_article_id=(
                            int(existing_draft["remote_article_id"])
                            if existing_draft
                            else None
                        ),
                    )
                )
            except Exception:
                logger.exception("Dev.to publish failed for account %s", account_id)
                results.append(
                    {
                        "status": "error",
                        "account_id": account_id,
                        "reason": "Publishing failed unexpectedly.",
                        "http_status": None,
                        "article_url": None,
                        "raw": None,
                    }
                )

        outcome = results[-1]
        draft_exists = bool(
            request.generation_id is not None
            and activity_store.find_latest_draft(request.generation_id, account_id)
        )
        if request.publish:
            action = "draft_published" if draft_exists else "post_published"
        else:
            action = "draft_updated" if draft_exists else "draft_saved"
        try:
            history_id = activity_store.record_publishing(
                generation_id=request.generation_id,
                account_id=account_id,
                account_name=account.get("label") if account else account_id,
                action=action,
                post=request.post,
                result=outcome,
            )
            outcome["history_id"] = history_id
            outcome["action"] = action
        except sqlite3.Error:
            logger.exception("Publishing history could not be saved for %s", account_id)

    if len(results) == 1:
        return results[0]

    statuses = [result["status"] for result in results]
    if all(status == "success" for status in statuses):
        overall_status = "success"
    elif all(status == "skipped" for status in statuses):
        overall_status = "skipped"
    elif "success" in statuses:
        overall_status = "partial"
    else:
        overall_status = "error"

    return {
        "status": overall_status,
        "results": results,
        "success_count": statuses.count("success"),
        "error_count": statuses.count("error"),
    }
