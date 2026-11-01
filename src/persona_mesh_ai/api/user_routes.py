"""User management routes (mounted at /api/v1/users).

Endpoints:
    GET    /api/v1/users              list users
    POST   /api/v1/users              create user
    POST   /api/v1/users/bulk         create users from JSON
    GET    /api/v1/users/{id}         fetch one
    PATCH  /api/v1/users/{id}         partial update (any field)
    DELETE /api/v1/users/{id}         delete
    GET    /api/v1/users/me           identify by X-API-Key header
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator

from . import activity_store, user_store

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = logging.getLogger(__name__)
BULK_JSON_BODY = Body(...)

MAX_BULK_USERS = 500
MAX_BULK_JSON_BYTES = 2 * 1024 * 1024
MAX_VALIDATION_ERRORS = 100


def _log_user_activity(*args: Any, **kwargs: Any) -> None:
    try:
        activity_store.log_event(*args, **kwargs)
    except sqlite3.Error:
        logger.exception("User activity could not be recorded")


class UserCreate(BaseModel):
    id: str = Field(min_length=1)
    name: str
    role: str
    description: str
    relationship: str
    personality: str
    api_key: str = Field(min_length=1)

    @field_validator(
        "id", "name", "role", "description", "relationship", "personality", "api_key"
    )
    @classmethod
    def require_nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty")
        return value


class UserUpdate(BaseModel):
    id: str | None = Field(default=None, min_length=1)
    name: str | None = None
    role: str | None = None
    description: str | None = None
    relationship: str | None = None
    personality: str | None = None
    api_key: str | None = Field(default=None, min_length=1)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("id cannot be empty")
        return value


@router.get("")
def list_users() -> list[dict[str, Any]]:
    return user_store.list_users()


@router.post("", status_code=201)
def create_user(body: UserCreate) -> dict[str, Any]:
    try:
        user = user_store.create_user(body.model_dump(exclude_none=True))
        _log_user_activity(
            "user_created",
            "user",
            f"Created user {user['name']}",
            entity_id=user["id"],
            actor_id=user["id"],
            actor_name=user["name"],
        )
        return user
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        logger.exception("User creation failed")
        raise HTTPException(status_code=500, detail="Could not create user") from exc


@router.post("/bulk", status_code=201)
def create_users_bulk(payload: Any = BULK_JSON_BODY) -> dict[str, Any]:
    """Create users from a JSON array or an object containing a users/personas array."""
    if isinstance(payload, list):
        raw_users = payload
    elif isinstance(payload, dict):
        raw_users = payload.get("users")
        if not isinstance(raw_users, list):
            raw_users = payload.get("personas")
        if not isinstance(raw_users, list):
            raw_users = None
    else:
        raw_users = None

    if raw_users is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a JSON array or an object with a 'users' or 'personas' array",
        )

    if not raw_users:
        raise HTTPException(status_code=422, detail="The users array cannot be empty")
    if len(raw_users) > MAX_BULK_USERS:
        raise HTTPException(
            status_code=413,
            detail=f"Import is limited to {MAX_BULK_USERS} users at a time",
        )

    try:
        payload_size = len(json.dumps(raw_users, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON data") from exc
    if payload_size > MAX_BULK_JSON_BYTES:
        raise HTTPException(
            status_code=413, detail="Import JSON exceeds the 2 MB limit"
        )

    validated_users: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    total_errors = 0
    for index, raw_user in enumerate(raw_users, start=1):
        try:
            user = UserCreate.model_validate(raw_user)
        except ValidationError as exc:
            for error in exc.errors():
                total_errors += 1
                if len(validation_errors) < MAX_VALIDATION_ERRORS:
                    validation_errors.append(
                        {
                            "index": index,
                            "field": ".".join(str(part) for part in error["loc"]),
                            "message": error["msg"],
                        }
                    )
        else:
            validated_users.append(user.model_dump())

    if total_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No users were created. Fix the listed rows and try again.",
                "errors": validation_errors,
                "truncated": total_errors > len(validation_errors),
            },
        )

    try:
        users = user_store.create_users(validated_users)
        for user in users:
            _log_user_activity(
                "user_created",
                "user",
                f"Created user {user['name']} from JSON import",
                entity_id=user["id"],
                actor_id=user["id"],
                actor_name=user["name"],
                details={"source": "json_import"},
            )
    except ValueError as exc:
        status_code = 409 if "already exists" in str(exc) else 422
        raise HTTPException(
            status_code=status_code,
            detail=f"No users were created: {exc}",
        ) from exc
    except sqlite3.Error as exc:
        logger.exception("Bulk user creation failed")
        raise HTTPException(
            status_code=500,
            detail="Could not create users. No users were created.",
        ) from exc

    return {"created_count": len(users), "users": users}


@router.get("/me")
def get_me(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    user = user_store.get_user_by_api_key(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


@router.get("/{user_id}")
def get_user(user_id: str) -> dict[str, Any]:
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}")
def update_user(user_id: str, body: UserUpdate) -> dict[str, Any]:
    try:
        user = user_store.update_user(user_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _log_user_activity(
        "user_updated",
        "user",
        f"Updated user {user['name']}",
        entity_id=user_id,
        actor_id=user_id,
        actor_name=user["name"],
        details={
            "fields": sorted(body.model_dump(exclude_unset=True).keys()),
            "previous_id": user_id,
            "new_id": user["id"],
        },
    )
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str) -> None:
    user = user_store.get_user(user_id)
    if not user or not user_store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    _log_user_activity(
        "user_deleted",
        "user",
        f"Deleted user {user['name']}",
        entity_id=user_id,
        actor_id=user_id,
        actor_name=user["name"],
    )
