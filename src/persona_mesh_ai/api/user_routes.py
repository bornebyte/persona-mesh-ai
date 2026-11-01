"""User management routes (mounted at /api/v1/users).

Endpoints:
    GET    /api/v1/users              list users
    POST   /api/v1/users              create user
    GET    /api/v1/users/{id}         fetch one
    PATCH  /api/v1/users/{id}         partial update (any field)
    DELETE /api/v1/users/{id}         delete
    GET    /api/v1/users/me           identify by X-API-Key header
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import user_store

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserCreate(BaseModel):
    id: str = Field(min_length=1)
    name: str
    role: str
    description: str
    relationship: str
    personality: str
    api_key: str = Field(min_length=1)


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    relationship: str | None = None
    personality: str | None = None
    api_key: str | None = Field(default=None, min_length=1)


@router.get("")
def list_users() -> list[dict[str, Any]]:
    return user_store.list_users()


@router.post("", status_code=201)
def create_user(body: UserCreate) -> dict[str, Any]:
    try:
        return user_store.create_user(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        user = user_store.update_user(
            user_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str) -> None:
    if not user_store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
