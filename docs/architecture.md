# Architecture Notes

The app is intentionally local and small:

- `backend/` exposes a FastAPI REST API backed by SQLite.
- `frontend/` is a React + Vite workspace that calls the local API.
- `backend/personas.py` contains seed definitions only.
- SQLite stores editable personas, councils, memories, posts, and comments.
- `backend/simulator.py` owns prompt construction, JSON validation, fallback generation, summaries, and memory updates.
- `backend/ollama_client.py` is the optional Ollama-compatible HTTP client.

## SQLite Model

Core tables:

- `posts`: original user posts, selected `council_id`, `discussion_summary`, selected `model`, and timestamps.
- `comments`: root comments and nested replies for each post.
- `personas`: editable persona profiles and active toggles.
- `councils`: editable council names, descriptions, and simulation style.
- `council_personas`: ordered council membership.
- `persona_memories`: one concise local summary memory per persona.

Startup runs lightweight migrations with `ALTER TABLE` for new post/persona columns and creates new v0.2 tables if missing. Default personas and councils are inserted with `INSERT OR IGNORE`, so restarts do not duplicate or overwrite user-edited records.

## Generation Flow

Generation follows a read, close, generate, write pattern:

1. Load the post, council, active council personas, persona memory, and existing comments.
2. Close the SQLite connection.
3. Call Ollama with strict JSON prompts.
4. Validate JSON shape, persona IDs, parent comment IDs, and content length.
5. Fall back deterministically if Ollama fails or returns invalid JSON.
6. Open a new SQLite connection and write comments, replies, summaries, or memory updates.

SQLite connections use a timeout, `PRAGMA busy_timeout`, foreign keys, and WAL mode. No connection is intentionally held while waiting on Ollama.

## Councils And Personas

Councils provide the simulation frame. The prompt includes council name, description, simulation style, selected persona profile, persona memory, original post, and existing comments where relevant.

Personas are regular SQLite rows with:

- `id`
- `name`
- `avatar_label`
- `personality`
- `interests`
- `speech_style`
- `role`
- `is_active`
- `created_at`
- `updated_at`

Inactive personas remain editable and visible but are excluded from new generation waves.

Default persona and council seed data can be restored per record. Persona reset restores profile fields and active state but keeps memory separate. Council reset restores name, description, simulation style, and ordered membership.

## Memory And Summaries

After reply waves and continued discussion, participating personas get memory updates. Memory is a short local summary capped to about 1000 characters. Discussion summaries are stored on `posts.discussion_summary` in a compact markdown-like structure:

```text
Key points:
- ...

Open questions:
- ...

Next step:
- ...
```

## Frontend

The React UI has three main areas:

- Left sidebar: new chat, council selector, thread history.
- Main workspace: current thread, summary, composer, model switcher, continue, delete, and markdown actions.
- Settings inspector: council fields, council membership, persona profile, memory editor, reset controls, and clear-memory action.

The send and continue flows use an in-flight ref plus disabled controls to prevent duplicate requests.

Destructive UI actions use browser confirmation before calling local delete/reset endpoints. Thread deletion relies on SQLite cascading deletes for comments.

## Fallback Behavior

If Ollama is offline, the configured model is missing, a request times out, or JSON validation fails, simulator functions return deterministic fallback content. Fallbacks are council-aware enough to keep the app usable without a model, but they are simpler and less varied than local model output.
