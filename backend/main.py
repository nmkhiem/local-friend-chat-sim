from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from db import get_connection, init_db, row_to_dict
from ollama_client import OllamaClient
from personas import Council, Persona
from schemas import (
    CommentOut,
    CouncilDetail,
    CouncilOut,
    CouncilUpdate,
    ModelSelect,
    PersonaMemoryIn,
    PersonaMemoryOut,
    PersonaOut,
    PersonaUpdate,
    PostCreate,
    PostDetail,
    PostOut,
)
from simulator import (
    generate_comment_batch,
    generate_discussion_summary,
    generate_memory_updates,
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


@app.get("/personas", response_model=list[PersonaOut])
def list_personas() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = _persona_rows(conn)
    return [_persona_out(row_to_dict(row)) for row in rows]


@app.get("/personas/{persona_id}", response_model=PersonaOut)
def get_persona(persona_id: str) -> dict[str, Any]:
    persona = _get_persona_or_404(persona_id)
    return persona


@app.put("/personas/{persona_id}", response_model=PersonaOut)
def update_persona(persona_id: str, payload: PersonaUpdate) -> dict[str, Any]:
    _get_persona_or_404(persona_id)
    updates = _payload_updates(payload)
    if updates:
        assignments: list[str] = []
        values: list[Any] = []
        for field, value in updates.items():
            assignments.append(f"{field} = ?")
            if field == "is_active":
                values.append(1 if value else 0)
            else:
                values.append(str(value).strip())
        values.append(persona_id)
        with get_connection() as conn:
            conn.execute(
                f"""
                UPDATE personas
                SET {", ".join(assignments)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                values,
            )
    return _get_persona_or_404(persona_id)


@app.get("/personas/{persona_id}/memory", response_model=PersonaMemoryOut)
def get_persona_memory(persona_id: str) -> dict[str, str]:
    _get_persona_or_404(persona_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT persona_id, memory, updated_at FROM persona_memories WHERE persona_id = ?",
            (persona_id,),
        ).fetchone()
    if row is None:
        return {"persona_id": persona_id, "memory": "", "updated_at": ""}
    return row_to_dict(row)


@app.put("/personas/{persona_id}/memory", response_model=PersonaMemoryOut)
def update_persona_memory(persona_id: str, payload: PersonaMemoryIn) -> dict[str, str]:
    _get_persona_or_404(persona_id)
    memory = " ".join(payload.memory.split())[:1000]
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO persona_memories (persona_id, memory, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(persona_id)
            DO UPDATE SET memory = excluded.memory, updated_at = CURRENT_TIMESTAMP
            """,
            (persona_id, memory),
        )
    return get_persona_memory(persona_id)


@app.get("/councils", response_model=list[CouncilOut])
def list_councils() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM councils ORDER BY created_at ASC, id ASC").fetchall()
        councils = [_council_out(conn, row_to_dict(row)) for row in rows]
    return councils


@app.get("/councils/{council_id}", response_model=CouncilDetail)
def get_council(council_id: str) -> dict[str, Any]:
    return _get_council_or_404(council_id)


@app.put("/councils/{council_id}", response_model=CouncilDetail)
def update_council(council_id: str, payload: CouncilUpdate) -> dict[str, Any]:
    _get_council_or_404(council_id)
    updates = _payload_updates(payload, skip={"persona_ids"})

    with get_connection() as conn:
        if updates:
            assignments = [f"{field} = ?" for field in updates]
            values = [str(value).strip() for value in updates.values()]
            values.append(council_id)
            conn.execute(
                f"""
                UPDATE councils
                SET {", ".join(assignments)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                values,
            )

        if payload.persona_ids is not None:
            persona_ids = _unique_nonempty(payload.persona_ids)
            if not persona_ids:
                raise HTTPException(status_code=400, detail="A council needs at least one persona.")
            missing = _missing_persona_ids(conn, persona_ids)
            if missing:
                raise HTTPException(status_code=400, detail=f"Unknown persona ids: {', '.join(missing)}")
            conn.execute("DELETE FROM council_personas WHERE council_id = ?", (council_id,))
            for index, persona_id in enumerate(persona_ids):
                conn.execute(
                    """
                    INSERT INTO council_personas (council_id, persona_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (council_id, persona_id, index),
                )
            conn.execute(
                "UPDATE councils SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (council_id,),
            )

    return _get_council_or_404(council_id)


@app.post("/posts", response_model=PostOut)
def create_post(payload: PostCreate) -> dict[str, Any]:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Post content is required.")

    council_id = (payload.council_id or "friend").strip() or "friend"
    _get_council_or_404(council_id)
    topic_summary = summarize_topic(content)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO posts (content, topic_summary, council_id, model)
            VALUES (?, ?, ?, ?)
            """,
            (content, topic_summary, council_id, ollama.model),
        )
        post_id = cursor.lastrowid

    return _get_post_or_404(post_id)


@app.get("/posts", response_model=list[PostOut])
def list_posts() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                p.*,
                COALESCE(c.name, p.council_id) AS council_name,
                COUNT(cm.id) AS comment_count
            FROM posts p
            LEFT JOIN councils c ON c.id = p.council_id
            LEFT JOIN comments cm ON cm.post_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT 50
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


@app.get("/posts/{post_id}", response_model=PostDetail)
def get_post(post_id: int) -> dict[str, Any]:
    return _post_detail(post_id)


@app.post("/posts/{post_id}/simulate", response_model=list[CommentOut])
async def simulate_comments(post_id: int) -> list[dict[str, Any]]:
    context = _generation_context(post_id)
    post = context["post"]
    council = context["council"]
    personas = select_comment_personas(post_id, post["content"], context["personas"])
    if not personas:
        raise HTTPException(status_code=400, detail="The selected council has no active personas.")

    generated_comments = await generate_comment_batch(
        ollama,
        council,
        personas,
        post["content"],
        post["topic_summary"],
    )
    created = _store_comments(post_id, generated_comments)
    await _update_summary_for_post(post_id)
    return created


@app.post("/posts/{post_id}/simulate-reply", response_model=list[CommentOut])
async def simulate_replies(post_id: int) -> list[dict[str, Any]]:
    context = _generation_context(post_id)
    post = context["post"]
    existing_comments = context["comments"]
    if not existing_comments:
        raise HTTPException(status_code=400, detail="Create comments before simulating replies.")

    personas = select_reply_personas(
        post_id,
        f"{post['content']}:{len(existing_comments)}",
        context["personas"],
    )
    if not personas:
        raise HTTPException(status_code=400, detail="The selected council has no active personas.")

    reply_tasks = _reply_tasks(post_id, personas, existing_comments)
    generated_replies = await generate_reply_batch(
        ollama,
        context["council"],
        personas,
        post["content"],
        _comments_for_prompt(existing_comments),
        reply_tasks,
    )
    created = _store_comments(post_id, generated_replies)
    await _update_summary_for_post(post_id)
    await _try_update_memories(post_id, {item["persona_id"] for item in generated_replies})
    return created


@app.post("/posts/{post_id}/continue", response_model=PostDetail)
async def continue_discussion(post_id: int) -> dict[str, Any]:
    context = _generation_context(post_id)
    post = context["post"]
    existing_comments = context["comments"]
    if not existing_comments:
        raise HTTPException(status_code=400, detail="Create comments before continuing discussion.")

    personas = select_reply_personas(
        post_id,
        f"{post['content']}:continue:{len(existing_comments)}",
        context["personas"],
    )
    if not personas:
        raise HTTPException(status_code=400, detail="The selected council has no active personas.")

    target_pool = existing_comments[-max(4, len(personas) * 2) :]
    reply_tasks = _reply_tasks(post_id + len(existing_comments), personas, target_pool)
    generated_replies = await generate_reply_batch(
        ollama,
        context["council"],
        personas,
        post["content"],
        _comments_for_prompt(existing_comments),
        reply_tasks,
    )
    unique_replies = _dedupe_generated(generated_replies, existing_comments)
    if unique_replies:
        _store_comments(post_id, unique_replies)
        await _update_summary_for_post(post_id)
        await _try_update_memories(post_id, {item["persona_id"] for item in unique_replies})

    return _post_detail(post_id)


@app.get("/posts/{post_id}/export.md")
def export_markdown(post_id: int) -> Response:
    detail = _post_detail(post_id)
    markdown = _thread_markdown(detail)
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


def _payload_updates(payload: Any, skip: set[str] | None = None) -> dict[str, Any]:
    skip = skip or set()
    return {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key not in skip and value is not None
    }


def _unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def _persona_rows(conn: Any) -> list[Any]:
    return conn.execute(
        """
        SELECT p.*, COALESCE(pm.memory, '') AS memory
        FROM personas p
        LEFT JOIN persona_memories pm ON pm.persona_id = p.id
        ORDER BY p.created_at ASC, p.id ASC
        """
    ).fetchall()


def _get_persona_or_404(persona_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*, COALESCE(pm.memory, '') AS memory
            FROM personas p
            LEFT JOIN persona_memories pm ON pm.persona_id = p.id
            WHERE p.id = ?
            """,
            (persona_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Persona not found.")
    return _persona_out(row_to_dict(row))


def _persona_out(row: dict[str, Any]) -> dict[str, Any]:
    row["is_active"] = bool(row.get("is_active", 1))
    row["avatar_label"] = row.get("avatar_label") or _initials(row.get("name", ""))
    row["role"] = row.get("role") or "participant"
    row["memory"] = row.get("memory") or ""
    row["created_at"] = row.get("created_at") or ""
    row["updated_at"] = row.get("updated_at") or ""
    return row


def _persona_from_row(row: dict[str, Any]) -> Persona:
    clean = _persona_out(dict(row))
    return Persona(
        id=clean["id"],
        name=clean["name"],
        avatar_label=clean["avatar_label"],
        personality=clean["personality"],
        interests=clean["interests"],
        speech_style=clean["speech_style"],
        role=clean["role"],
        is_active=clean["is_active"],
        memory=clean["memory"],
    )


def _missing_persona_ids(conn: Any, persona_ids: list[str]) -> list[str]:
    placeholders = ",".join("?" for _ in persona_ids)
    rows = conn.execute(f"SELECT id FROM personas WHERE id IN ({placeholders})", persona_ids).fetchall()
    found = {row["id"] for row in rows}
    return [persona_id for persona_id in persona_ids if persona_id not in found]


def _council_out(conn: Any, row: dict[str, Any]) -> dict[str, Any]:
    row["persona_ids"] = _council_persona_ids(conn, row["id"])
    return row


def _get_council_or_404(council_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM councils WHERE id = ?", (council_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Council not found.")
        detail = _council_out(conn, row_to_dict(row))
        detail["personas"] = _personas_for_council(conn, council_id, active_only=False)
    return detail


def _council_persona_ids(conn: Any, council_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT persona_id
        FROM council_personas
        WHERE council_id = ?
        ORDER BY position ASC, persona_id ASC
        """,
        (council_id,),
    ).fetchall()
    return [row["persona_id"] for row in rows]


def _personas_for_council(conn: Any, council_id: str, active_only: bool) -> list[dict[str, Any]]:
    active_clause = "AND p.is_active = 1" if active_only else ""
    rows = conn.execute(
        f"""
        SELECT p.*, COALESCE(pm.memory, '') AS memory
        FROM council_personas cp
        JOIN personas p ON p.id = cp.persona_id
        LEFT JOIN persona_memories pm ON pm.persona_id = p.id
        WHERE cp.council_id = ?
        {active_clause}
        ORDER BY cp.position ASC, p.id ASC
        """,
        (council_id,),
    ).fetchall()
    return [_persona_out(row_to_dict(row)) for row in rows]


def _council_from_detail(detail: dict[str, Any]) -> Council:
    return Council(
        id=detail["id"],
        name=detail["name"],
        description=detail["description"],
        simulation_style=detail["simulation_style"],
        persona_ids=tuple(detail["persona_ids"]),
    )


def _get_post_or_404(post_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                p.*,
                COALESCE(c.name, p.council_id) AS council_name,
                COUNT(cm.id) AS comment_count
            FROM posts p
            LEFT JOIN councils c ON c.id = p.council_id
            LEFT JOIN comments cm ON cm.post_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (post_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    return row_to_dict(row)


def _post_detail(post_id: int) -> dict[str, Any]:
    post = _get_post_or_404(post_id)
    post["council"] = _get_council_or_404(post["council_id"])
    post["comments"] = _comments_for_post(post_id)
    return post


def _generation_context(post_id: int) -> dict[str, Any]:
    post = _get_post_or_404(post_id)
    council_detail = _get_council_or_404(post["council_id"])
    with get_connection() as conn:
        persona_rows = _personas_for_council(conn, post["council_id"], active_only=True)
        comments = _flat_comments_for_post(conn, post_id)
    return {
        "post": post,
        "council": _council_from_detail(council_detail),
        "personas": [_persona_from_row(row) for row in persona_rows],
        "comments": comments,
    }


def _flat_comments_for_post(conn: Any, post_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.*,
            COALESCE(p.name, c.author_persona_id) AS author_name,
            COALESCE(p.avatar_label, '') AS author_avatar_label
        FROM comments c
        LEFT JOIN personas p ON p.id = c.author_persona_id
        WHERE c.post_id = ?
        ORDER BY c.created_at ASC, c.id ASC
        """,
        (post_id,),
    ).fetchall()

    comments: list[dict[str, Any]] = []
    for row in rows:
        comment = row_to_dict(row)
        comment["replies"] = []
        comments.append(comment)
    return comments


def _comments_for_post(post_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        flat_comments = _flat_comments_for_post(conn, post_id)

    comments: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for comment in flat_comments:
        comments[comment["id"]] = comment

    for comment in comments.values():
        parent_id = comment["parent_comment_id"]
        if parent_id and parent_id in comments:
            comments[parent_id]["replies"].append(comment)
        else:
            roots.append(comment)

    return roots


def _comments_for_prompt(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": comment["id"],
            "persona_id": comment["author_persona_id"],
            "persona_name": comment["author_name"],
            "parent_comment_id": comment["parent_comment_id"],
            "content": comment["content"],
        }
        for comment in comments[-50:]
    ]


def _reply_tasks(seed: int, personas: list[Persona], comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, persona in enumerate(personas):
        candidates = [comment for comment in comments if comment["author_persona_id"] != persona.id] or comments
        target = candidates[(seed + index) % len(candidates)]
        tasks.append(
            {
                "persona_id": persona.id,
                "persona_name": persona.name,
                "role": persona.role,
                "personality": persona.personality,
                "interests": persona.interests,
                "speech_style": persona.speech_style,
                "memory": persona.memory,
                "parent_comment_id": target["id"],
                "target_comment": target["content"],
            }
        )
    return tasks


def _store_comments(post_id: int, generated_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    with get_connection() as conn:
        for generated in generated_items:
            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, author_persona_id, parent_comment_id, content)
                VALUES (?, ?, ?, ?)
                """,
                (
                    post_id,
                    generated["persona_id"],
                    generated.get("parent_comment_id"),
                    generated["content"],
                ),
            )
            created.append(_comment_by_id(conn, cursor.lastrowid))
    return created


def _comment_by_id(conn: Any, comment_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            c.*,
            COALESCE(p.name, c.author_persona_id) AS author_name,
            COALESCE(p.avatar_label, '') AS author_avatar_label
        FROM comments c
        LEFT JOIN personas p ON p.id = c.author_persona_id
        WHERE c.id = ?
        """,
        (comment_id,),
    ).fetchone()
    comment = row_to_dict(row)
    comment["replies"] = []
    return comment


async def _update_summary_for_post(post_id: int) -> None:
    context = _generation_context(post_id)
    comments = context["comments"]
    if not comments:
        return

    summary = await generate_discussion_summary(
        ollama,
        context["council"],
        context["post"]["content"],
        _comments_for_prompt(comments),
    )
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE posts
            SET discussion_summary = ?, model = ?
            WHERE id = ?
            """,
            (summary, ollama.model, post_id),
        )


async def _try_update_memories(post_id: int, participating_persona_ids: set[str]) -> None:
    try:
        await _update_memories(post_id, participating_persona_ids)
    except Exception:
        return


async def _update_memories(post_id: int, participating_persona_ids: set[str]) -> None:
    if not participating_persona_ids:
        return
    post = _get_post_or_404(post_id)
    council_detail = _get_council_or_404(post["council_id"])
    with get_connection() as conn:
        comments = _flat_comments_for_post(conn, post_id)
        personas = _personas_by_ids(conn, list(participating_persona_ids))
    if not personas or not comments:
        return

    updates = await generate_memory_updates(
        ollama,
        _council_from_detail(council_detail),
        personas,
        post["content"],
        post["discussion_summary"],
        _comments_for_prompt(comments),
    )
    if not updates:
        return

    with get_connection() as conn:
        for persona_id, memory in updates.items():
            conn.execute(
                """
                INSERT INTO persona_memories (persona_id, memory, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(persona_id)
                DO UPDATE SET memory = excluded.memory, updated_at = CURRENT_TIMESTAMP
                """,
                (persona_id, memory[:1000]),
            )


def _personas_by_ids(conn: Any, persona_ids: list[str]) -> list[Persona]:
    persona_ids = _unique_nonempty(persona_ids)
    if not persona_ids:
        return []
    placeholders = ",".join("?" for _ in persona_ids)
    rows = conn.execute(
        f"""
        SELECT p.*, COALESCE(pm.memory, '') AS memory
        FROM personas p
        LEFT JOIN persona_memories pm ON pm.persona_id = p.id
        WHERE p.id IN ({placeholders})
        """,
        persona_ids,
    ).fetchall()
    by_id = {row["id"]: _persona_from_row(row_to_dict(row)) for row in rows}
    return [by_id[persona_id] for persona_id in persona_ids if persona_id in by_id]


def _dedupe_generated(
    generated: list[dict[str, Any]],
    existing_comments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {_normalize_text(comment["content"]) for comment in existing_comments}
    unique: list[dict[str, Any]] = []
    for item in generated:
        normalized = _normalize_text(item["content"])
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return unique


def _normalize_text(value: str) -> str:
    return " ".join(re for re in "".join(char.lower() if char.isalnum() else " " for char in value).split())


def _thread_markdown(detail: dict[str, Any]) -> str:
    lines = [
        "# Local Friend Chat Thread",
        "",
        "## Original post",
        "",
        detail["content"],
        "",
        "## Council",
        "",
        f"**{detail['council_name']}**",
    ]
    council = detail.get("council") or {}
    if council.get("description"):
        lines.extend(["", council["description"]])
    if council.get("simulation_style"):
        lines.extend(["", f"_Style: {council['simulation_style']}_"])

    lines.extend(["", "## Discussion", ""])
    if detail["comments"]:
        lines.extend(_comment_markdown(detail["comments"]))
    else:
        lines.append("_No simulated comments yet._")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            detail.get("discussion_summary") or "_No summary generated yet._",
            "",
            "## Metadata",
            "",
            f"- Created at: {detail['created_at']}",
            f"- Council: {detail['council_name']}",
            f"- Model: {detail.get('model') or 'fallback/unspecified'}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _comment_markdown(comments: list[dict[str, Any]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for comment in comments:
        label = "replied" if depth else ""
        name = comment["author_name"]
        prefix = f"{indent}- " if depth else ""
        if label:
            lines.append(f"{prefix}**{name} replied:** {comment['content']}")
        else:
            lines.append(f"**{name}:** {comment['content']}")
        if comment.get("replies"):
            lines.extend(_comment_markdown(comment["replies"], depth + 1))
    return lines


def _initials(name: str) -> str:
    return "".join(part[0] for part in name.split() if part)[:2].upper() or "?"
