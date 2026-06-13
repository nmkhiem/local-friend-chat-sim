from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db import get_connection, init_db, row_to_dict
from ollama_client import OllamaClient
from personas import PERSONAS
from schemas import CommentOut, PostCreate, PostDetail, PostOut
from simulator import (
    generate_comment,
    generate_reply,
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
    created: list[dict[str, Any]] = []

    with get_connection() as conn:
        for persona in personas:
            content = await generate_comment(ollama, persona, post["content"], post["topic_summary"])
            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, author_persona_id, parent_comment_id, content)
                VALUES (?, ?, NULL, ?)
                """,
                (post_id, persona.id, content),
            )
            created.append(_comment_by_id(conn, cursor.lastrowid))

    return created


@app.post("/posts/{post_id}/simulate-reply", response_model=list[CommentOut])
async def simulate_replies(post_id: int) -> list[dict[str, Any]]:
    post = _get_post_or_404(post_id)

    with get_connection() as conn:
        existing_comments = conn.execute(
            """
            SELECT * FROM comments
            WHERE post_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (post_id,),
        ).fetchall()

        if not existing_comments:
            raise HTTPException(status_code=400, detail="Create comments before simulating replies.")

        personas = select_reply_personas(post_id, f"{post['content']}:{len(existing_comments)}")
        created: list[dict[str, Any]] = []
        for index, persona in enumerate(personas):
            target = existing_comments[index % len(existing_comments)]
            content = await generate_reply(ollama, persona, post["content"], target["content"])
            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, author_persona_id, parent_comment_id, content)
                VALUES (?, ?, ?, ?)
                """,
                (post_id, persona.id, target["id"], content),
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
