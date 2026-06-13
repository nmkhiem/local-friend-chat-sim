# Local Friend Chat Simulator

A local-first council simulator for trying ideas against small simulated groups. The app stores everything in SQLite, uses editable personas and reusable councils, and calls either an Ollama local model or an OpenAI-compatible API key provider for generation. If generation fails or returns invalid JSON, the API returns an error instead of synthetic template text.

## What v0.2 Adds

- Council mode with seeded Friend, Research, Product, Study, and Harsh Review councils.
- SQLite-backed editable personas with roles, avatar labels, personality, interests, speech style, and active toggles.
- Simple per-persona summary memory stored locally in SQLite.
- Thread history with council metadata and comment counts.
- Continue discussion endpoint and UI action.
- Markdown export for a complete thread.
- Short structured discussion summaries.
- Optional API-key generation provider for faster or higher-quality hosted models.

## Project Structure

- `backend/` - FastAPI, SQLite migrations/seeding, persona simulation, and model provider clients.
- `frontend/` - React + Vite council workspace UI.
- `docs/` - lightweight architecture notes.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API runs at `http://localhost:8000` by default.

Useful checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/personas
curl http://localhost:8000/councils
curl -X POST http://localhost:8000/posts \
  -H "Content-Type: application/json" \
  -d '{"content":"I want to explore world models for healthcare research. What are the weak assumptions?", "council_id":"research"}'
```

Smoke test the v0.2 backend flow after the server is running:

```bash
./scripts/smoke_backend.sh
```

To target another backend URL:

```bash
API_BASE_URL=http://localhost:8000 ./scripts/smoke_backend.sh
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The Vite app runs at `http://localhost:5173` by default.

To point the frontend at another backend URL:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Council Mode

A council is a reusable simulation group with:

- `id`
- `name`
- `description`
- `simulation_style`
- `persona_ids`
- `created_at`
- `updated_at`

Default councils are seeded idempotently on startup. Existing user edits are not overwritten. New posts default to `friend` when no `council_id` is supplied.

## Persona Memory

Each persona can have one concise memory row in `persona_memories`. Memory is included in future prompts for that persona, updated after reply waves and continued discussions, and capped to about 1000 characters. This is simple summary memory, not vector search.

## Ollama

Install and run Ollama locally, then pull a model:

```bash
ollama pull llama3.2:3b
ollama serve
```

The backend uses:

- `OLLAMA_BASE_URL`, default `http://localhost:11434`
- `OLLAMA_MODEL`, default `llama3.1`
- `OLLAMA_MODEL_OPTIONS`, optional comma-separated list shown in the UI as model choices
- `OLLAMA_TIMEOUT`, default `120`
- `OLLAMA_PULL_TIMEOUT`, default `600`

The model switcher can display installed models, configured missing models, switch the active model, and optionally trigger an Ollama pull. If `OLLAMA_MODEL` is not installed, the backend auto-selects the first installed model from the configured options. Do not pull large models unless you actually want them locally.

## Groq API Provider

Groq is supported as a dedicated provider through its OpenAI-compatible chat completions API:

```bash
cd backend
source .venv/bin/activate
MODEL_PROVIDER=groq \
GROQ_API_KEY=gsk-your-key \
GROQ_MODEL=llama-3.3-70b-versatile \
uvicorn main:app --reload
```

Supported Groq settings:

- `GROQ_API_KEY`, required when using `MODEL_PROVIDER=groq`.
- `GROQ_MODEL`, default `llama-3.3-70b-versatile`.
- `GROQ_BASE_URL`, default `https://api.groq.com/openai/v1`.
- `GROQ_TIMEOUT`, default `60`.

The frontend model switcher includes `Groq API` once the backend is restarted.

## OpenAI-Compatible API Provider

You can use an OpenAI-compatible chat completions API instead of Ollama. Keep the key on the backend only:

```bash
cd backend
source .venv/bin/activate
MODEL_PROVIDER=openai \
OPENAI_API_KEY=sk-your-key \
OPENAI_MODEL=gpt-4o-mini \
uvicorn main:app --reload
```

Supported API provider settings:

- `MODEL_PROVIDER`, default `ollama`; set to `openai` for the API-key provider.
- `OPENAI_API_KEY`, required when using `MODEL_PROVIDER=openai`.
- `OPENAI_MODEL`, default `gpt-4o-mini`.
- `OPENAI_BASE_URL`, default `https://api.openai.com/v1`; change this for other OpenAI-compatible gateways.
- `OPENAI_TIMEOUT`, default `60`.

The frontend model switcher has an `Ollama local` / `Groq API` / `API key` dropdown. It never receives or stores API keys. If you switch to a hosted provider without setting its API key, generation fails with a clear backend error.

## API

- `GET /health`
- `GET /models`
- `POST /models`
- `POST /models/pull`
- `GET /personas`
- `GET /personas/{persona_id}`
- `PUT /personas/{persona_id}`
- `POST /personas/{persona_id}/reset`
- `GET /personas/{persona_id}/memory`
- `PUT /personas/{persona_id}/memory`
- `DELETE /personas/{persona_id}/memory`
- `GET /councils`
- `GET /councils/{council_id}`
- `PUT /councils/{council_id}`
- `POST /councils/{council_id}/reset`
- `POST /posts`
- `GET /posts`
- `GET /posts/{post_id}`
- `DELETE /posts/{post_id}`
- `POST /posts/{post_id}/simulate`
- `POST /posts/{post_id}/simulate-reply`
- `POST /posts/{post_id}/continue`
- `GET /posts/{post_id}/export.md`

## Known Limitations

- SQLite is local only; there is no auth, sync, account system, or deployment layer.
- Persona memory is a short summary, not vector retrieval or durable fact management.
- Personas are simulated and can be inconsistent, especially with small local models.
- Local model speed and quality depend on hardware and the selected Ollama model.
- Generation requires the selected provider to be configured and return valid JSON; there is no synthetic template text path.
