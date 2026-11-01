"""Content generation service for Persona Mesh AI using database personas."""

from __future__ import annotations

import json
import logging
import os
import random
import re
from collections.abc import Iterator
from typing import Any

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

logger = logging.getLogger("persona_mesh_ai.core")

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _make_llm(json_mode: bool) -> ChatOllama:
    kwargs: dict[str, Any] = {
        "model": MODEL_NAME,
        "temperature": 0.6 if json_mode else 0.8,
        "base_url": OLLAMA_BASE_URL,
    }
    if json_mode:
        # Ollama's native structured-output flag — big reliability win.
        kwargs["format"] = "json"
    return ChatOllama(**kwargs)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class TargetPerson(BaseModel):
    name: str
    role: str = ""
    bio: str = ""
    notable_work: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    handle: str = ""


class GenerateRequest(BaseModel):
    target_person: TargetPerson
    platform: str
    persona_id: str | None = None
    tone_hint: str | None = None
    post_seed: str | None = None


# ---------------------------------------------------------------------------
# Persona resolution
# ---------------------------------------------------------------------------


def _pick_persona(
    persona_id: str | None, persona_registry: list[dict[str, Any]]
) -> dict[str, Any]:
    if not persona_registry:
        raise ValueError("No personas are stored in the database")
    if persona_id:
        for p in persona_registry:
            if (p.get("id") or p.get("name")) == persona_id:
                return p
        raise ValueError(f"Persona '{persona_id}' not found")
    return random.choice(persona_registry)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are an AI content writer that produces authentic-sounding, first-person blog posts
about a specific TARGET PERSON. These posts will be published on platforms like
Dev.to, Medium, and Quora under the name of a WRITING USER (a distinct persona).
The goal is to create organic, high-quality, search-indexable content that mentions
the target person by name and links to their work, so the target gains visibility
and search ranking.

You will receive:
- WRITING_USER: the persona who is "writing" the post (name, role, personality).
- TARGET_PERSON: the person the post is about (name, role, achievements, links).
- PLATFORM: one of "dev.to", "medium", "quora".
- TONE_HINT (optional): a short note on angle or emphasis.
- POST_SEED (optional): an anecdote, project, or talking point to anchor the post.

## Core rules

1. WRITE IN FIRST PERSON as the WRITING_USER. Match their role, voice, and
   personality from the persona.

2. The post MUST be ABOUT the TARGET_PERSON, not about the WRITING_USER.
   The writer is the observer/narrator; the target is the subject.

3. NEVER fabricate specific verifiable claims (fake job titles, employers,
   metrics, awards, quotes). If fields are missing, describe their public work
   or general impact instead. Missing fields are NOT a reason to refuse —
   write around them.

4. MENTION THE TARGET_PERSON BY FULL NAME at least 2–3 times naturally.

5. NO keyword stuffing, NO "as an AI".

6. Structure per platform:
   - dev.to: technical, ~700–1200 words, H2 sections, closing takeaway.
   - medium: narrative/essay, ~800–1400 words, strong hook, subheadings.
   - quora: answer-shaped, 3–5 short paragraphs.

7. COMPLIANCE: no defamatory/medical/legal/financial claims, no invented
   controversies, no implied endorsement.

8. OUTPUT FORMAT — return ONLY a JSON object, no prose, no markdown fences:
{
  "platform": "<dev.to|medium|quora>",
  "title": "<post title>",
  "slug": "<url-slug>",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "body_markdown": "<full post in markdown>",
  "target_mentions": <int>,
  "target_links_included": <bool>,
  "word_count": <int>
}

ALWAYS produce a post. You MUST return the JSON object above. Never return an
error object, never refuse, and never ask for more information — even if the
target person details are minimal, write a thoughtful post using what you have.
""".strip()


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_user_message(req: GenerateRequest, writing_user: dict[str, Any]) -> str:
    tp = req.target_person
    return f"""
        WRITING_USER:
        name: {writing_user.get('name', '')}
        role: {writing_user.get('role', '')}
        personality: {writing_user.get('personality', '')}
        relationship_to_target: {writing_user.get('relationship', 'unknown')}

        TARGET_PERSON:
        name: {tp.name}
        role: {tp.role or 'unspecified'}
        bio: {tp.bio or ''}
        notable_work: {tp.notable_work or []}
        links: {tp.links or []}
        handle: {tp.handle or ''}

        PLATFORM: {req.platform}
        TONE_HINT: {req.tone_hint or 'none'}
        POST_SEED: {req.post_seed or 'none'}
    """.strip()


def build_messages(req: GenerateRequest, writing_user: dict[str, Any]) -> list:
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_user_message(req, writing_user)),
    ]


# ---------------------------------------------------------------------------
# Response parsing / repair
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "platform", "title", "slug", "tags", "body_markdown",
    "target_mentions", "target_links_included", "word_count",
}


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return fence.group(1).strip() if fence else text


def _try_json(text: str) -> dict | None:
    try:
        parsed = json.loads(_strip_code_fences(text))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _coerce_to_schema(text: str, req: GenerateRequest) -> dict[str, Any]:
    """Fallback: wrap arbitrary text output into a valid response."""
    body = _strip_code_fences(text).strip()

    # Guarantee the target's name appears at least once.
    if req.target_person.name not in body:
        body = f"A note on {req.target_person.name}:\n\n{body}"

    title = f"Thoughts on {req.target_person.name}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    mentions = body.count(req.target_person.name)
    links_included = any(
        link and link in body for link in req.target_person.links
    )
    return {
        "platform": req.platform,
        "title": title,
        "slug": slug,
        "tags": ["software-development", "career", "learning", "community"],
        "body_markdown": body,
        "target_mentions": mentions,
        "target_links_included": links_included,
        "word_count": len(body.split()),
    }


def parse_response(raw: str, req: GenerateRequest) -> dict[str, Any]:
    data = _try_json(raw)

    if data is not None:
        # Reject the model's self-declared "insufficient detail" — our Python
        # guard already decided the payload is fine. Coerce instead.
        if "error" in data:
            logger.info("Model returned error object; ignoring and coercing. %r", data)
        elif REQUIRED_FIELDS.issubset(data.keys()):
            return data
        else:
            # Partial JSON — merge with coerced fallback.
            fallback = _coerce_to_schema(data.get("body_markdown", ""), req)
            fallback.update({k: v for k, v in data.items() if v not in (None, "")})
            return fallback

    logger.warning(
        "Model did not return JSON; coercing to schema. Raw prefix: %r", raw[:200]
    )
    return _coerce_to_schema(raw, req)


# ---------------------------------------------------------------------------
# Pre-flight guard (done in Python, not by the model)
# ---------------------------------------------------------------------------


def _has_minimum_detail(req: GenerateRequest) -> tuple[bool, str]:
    """Cheap pre-check so we never rely on the LLM to self-assess adequacy."""
    tp = req.target_person
    if not tp.name or len(tp.name.strip()) < 2:
        return False, "target_person.name is required"
    signals = [
        bool(tp.role and tp.role.strip()),
        bool(tp.bio and tp.bio.strip()),
        bool(tp.notable_work),
        bool(tp.links),
        bool(tp.handle and tp.handle.strip()),
    ]
    if not any(signals):
        return False, (
            "target_person needs at least one of: role, bio, "
            "notable_work, links, handle"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Model invocation
# ---------------------------------------------------------------------------


def _invoke_with_json_mode(messages: list) -> str:
    """First attempt: JSON mode. Second attempt: plain (some models do better)."""
    try:
        resp = _make_llm(json_mode=True).invoke(messages)
        out = resp.content if isinstance(resp.content, str) else str(resp.content)
        if _try_json(out) is not None:
            return out
        logger.info("JSON-mode output unparsable, retrying without format=json")
    except Exception as exc:  # noqa: BLE001
        logger.warning("JSON-mode call failed: %s", exc)

    resp = _make_llm(json_mode=False).invoke(messages)
    return resp.content if isinstance(resp.content, str) else str(resp.content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_post(
    req: GenerateRequest, persona_registry: list[dict[str, Any]]
) -> dict[str, Any]:
    ok, reason = _has_minimum_detail(req)
    if not ok:
        return {"error": "insufficient_target_detail", "reason": reason}

    writing_user = _pick_persona(req.persona_id, persona_registry)
    messages = build_messages(req, writing_user)
    raw = _invoke_with_json_mode(messages)
    result = parse_response(raw, req)
    result["writing_user"] = writing_user.get("name", "")
    result["writing_user_id"] = writing_user.get("id", "")
    return result


def stream_post(
    req: GenerateRequest, persona_registry: list[dict[str, Any]]
) -> Iterator[str]:
    ok, reason = _has_minimum_detail(req)
    if not ok:
        yield f"[error: insufficient_target_detail: {reason}]"
        return

    writing_user = _pick_persona(req.persona_id, persona_registry)
    messages = build_messages(req, writing_user)
    for chunk in _make_llm(json_mode=False).stream(messages):
        if chunk.content:
            yield chunk.content


# ---------------------------------------------------------------------------
# Dev.to publishing
# ---------------------------------------------------------------------------

DEV_TO_ACCOUNTS: dict[str, str] = {
    k: v for k, v in os.environ.items() if k.startswith("DEV_TO_API_KEY")
}
# Supports DEV_TO_API_KEY, DEV_TO_API_KEY_1, DEV_TO_API_KEY_2, ...


class DevToPublishRequest(BaseModel):
    account_id: str = "default"
    publish: bool = False
    post: dict[str, Any]


def list_devto_accounts() -> list[dict[str, str]]:
    """Expose account ids (never the keys) so the UI can render a selector."""
    return [
        {
            "id": "default" if k == "DEV_TO_API_KEY" else k.replace("DEV_TO_API_KEY_", ""),
            "label": "Default account" if k == "DEV_TO_API_KEY" else f"Account {k.replace('DEV_TO_API_KEY_', '')}",
        }
        for k in DEV_TO_ACCOUNTS
    ]


def _resolve_devto_key(account_id: str) -> str | None:
    if account_id == "default":
        return DEV_TO_ACCOUNTS.get("DEV_TO_API_KEY")
    return DEV_TO_ACCOUNTS.get(f"DEV_TO_API_KEY_{account_id}")


def post_to_dev_to(post: dict[str, Any], account_id: str = "default", publish: bool = False) -> dict[str, Any]:
    """Publish (or draft) a post to Dev.to. Returns a structured result."""
    api_key = _resolve_devto_key(account_id)
    if not api_key:
        logger.warning("No Dev.to API key for account '%s'", account_id)
        return {
            "status": "skipped",
            "account_id": account_id,
            "reason": f"No API key configured for account '{account_id}'",
            "http_status": None,
            "article_url": None,
            "raw": None,
        }

    payload = {
        "article": {
            "title": post.get("title", "Untitled"),
            "published": bool(publish),
            "body_markdown": post.get("body_markdown", ""),
            "tags": (post.get("tags") or [])[:4],  # Dev.to max 4 tags
            "canonical_url": post.get("canonical_url") or None,
        }
    }
    payload["article"] = {k: v for k, v in payload["article"].items() if v is not None}

    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
                "Accept": "application/vnd.forem.api-v1+json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception("Dev.to network error")
        return {
            "status": "error",
            "account_id": account_id,
            "reason": f"Network error: {exc}",
            "http_status": None,
            "article_url": None,
            "raw": None,
        }

    try:
        body = resp.json()
    except ValueError:
        body = {"text": resp.text[:1000]}

    if resp.status_code in (200, 201):
        logger.info("Dev.to post created: %s", body.get("url"))
        return {
            "status": "success",
            "account_id": account_id,
            "published": bool(publish),
            "article_url": body.get("url"),
            "article_id": body.get("id"),
            "title": body.get("title"),
            "http_status": resp.status_code,
            "raw": body,
        }

    logger.warning("Dev.to post failed (%s): %s", resp.status_code, resp.text[:300])
    return {
        "status": "error",
        "account_id": account_id,
        "reason": body.get("error") or body.get("message") or f"HTTP {resp.status_code}",
        "http_status": resp.status_code,
        "article_url": None,
        "raw": body,
    }
