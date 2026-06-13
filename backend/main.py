from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db import get_connection, init_db, row_to_dict
from ollama_client import OllamaClient
from personas import PERSONAS
from schemas import CommentOut, ModelSelect, PostCreate, PostDetail, PostOut
from simulator import (
    generate_comment_batch,
    generate_reply_batch,
    select_comment_personas,
    select_reply_personas,
    summarize_topic,
)


app = FastAPI(title="Local Friend Chat Simulator")
ollama = OllamaClient()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
async def list_models() -> dict[str, Any]:
    return await ollama.model_status()


@app.post("/models")
async def select_model(payload: ModelSelect) -> dict[str, Any]:
    try:
        ollama.set_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await ollama.model_status()


@app.post("/models/pull")
async def pull_model(payload: ModelSelect) -> dict[str, Any]:
    try:
        pulled = await ollama.pull_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pulled:
        raise HTTPException(status_code=502, detail="Could not download model from Ollama.")
    return await ollama.model_status()


@app.post("/posts", response_model=PostOut)
def create_post(payload: PostCreate) -> dict[str, Any]:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Post content is required.")

    topic_summary = summarize_topic(content)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO posts (content, topic_summary) VALUES (?, ?)",
            (content, topic_summary),
        )
        post_id = cursor.lastrowid
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

    return row_to_dict(post)


@app.get("/posts", response_model=list[PostOut])
def list_posts() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM posts ORDER BY created_at DESC, id DESC LIMIT 25").fetchall()
    return [row_to_dict(row) for row in rows]


@app.get("/posts/{post_id}", response_model=PostDetail)
def get_post(post_id: int) -> dict[str, Any]:
    post = _get_post_or_404(post_id)
    post["comments"] = _comments_for_post(post_id)
    return post


@app.post("/posts/{post_id}/simulate", response_model=list[CommentOut])
async def simulate_comments(post_id: int) -> list[dict[str, Any]]:
    post = _get_post_or_404(post_id)
    personas = select_comment_personas(post_id, post["content"])
    generated_comments = await generate_comment_batch(ollama, personas, post["content"], post["topic_summary"])
    created: list[dict[str, Any]] = []

    with get_connection() as conn:
        for generated in generated_comments:
            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, author_persona_id, parent_comment_id, content)
                VALUES (?, ?, NULL, ?)
                """,
                (post_id, generated["persona_id"], generated["content"]),
            )
            created.append(_comment_by_id(conn, cursor.lastrowid))

    return created


@app.post("/posts/{post_id}/simulate-reply", response_model=list[CommentOut])
async def simulate_replies(post_id: int) -> list[dict[str, Any]]:
    post = _get_post_or_404(post_id)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM comments
            WHERE post_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (post_id,),
        ).fetchall()

    existing_comments = [row_to_dict(row) for row in rows]
    if not existing_comments:
        raise HTTPException(status_code=400, detail="Create comments before simulating replies.")

    personas = select_reply_personas(post_id, f"{post['content']}:{len(existing_comments)}")
    comments_for_prompt = [
        {
            "id": comment["id"],
            "persona_id": comment["author_persona_id"],
            "content": comment["content"],
        }
        for comment in existing_comments
    ]
    reply_tasks = []
    for index, persona in enumerate(personas):
        target = existing_comments[index % len(existing_comments)]
        reply_tasks.append(
            {
                "persona_id": persona.id,
                "persona_name": persona.name,
                "personality": persona.personality,
                "speech_style": persona.speech_style,
                "parent_comment_id": target["id"],
                "target_comment": target["content"],
            }
        )

    generated_replies = await generate_reply_batch(ollama, post["content"], comments_for_prompt, reply_tasks)
    created: list[dict[str, Any]] = []

    with get_connection() as conn:
        for generated in generated_replies:
            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, author_persona_id, parent_comment_id, content)
                VALUES (?, ?, ?, ?)
                """,
                (
                    post_id,
                    generated["persona_id"],
                    generated["parent_comment_id"],
                    generated["content"],
                ),
            )
            created.append(_comment_by_id(conn, cursor.lastrowid))

    return created


def _get_post_or_404(post_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    return row_to_dict(row)


def _comment_by_id(conn: Any, comment_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    comment = row_to_dict(row)
    comment["author_name"] = PERSONAS[comment["author_persona_id"]].name
    comment["replies"] = []
    return comment


def _comments_for_post(post_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM comments
            WHERE post_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (post_id,),
        ).fetchall()

    comments: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        comment = row_to_dict(row)
        persona = PERSONAS.get(comment["author_persona_id"])
        comment["author_name"] = persona.name if persona else comment["author_persona_id"]
        comment["replies"] = []
        comments[comment["id"]] = comment

    for comment in comments.values():
        parent_id = comment["parent_comment_id"]
        if parent_id and parent_id in comments:
            comments[parent_id]["replies"].append(comment)
        else:
            roots.append(comment)

    return roots
