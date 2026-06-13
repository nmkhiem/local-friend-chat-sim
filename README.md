# Local Friend Chat Simulator

A local-first MVP that lets you share a text post and simulate a small friend group discussing it. The backend stores posts and comments in SQLite, uses static personas, and tries an Ollama-compatible local HTTP API for generation. If Ollama is not running, it returns deterministic fallback comments and replies.

## Project Structure

- `backend/` - FastAPI, SQLite, persona simulation, optional Ollama client.
- `frontend/` - React + Vite UI.
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
curl -X POST http://localhost:8000/posts \
  -H "Content-Type: application/json" \
  -d '{"content":"I just read about world models in AI and wonder how they can be used for planning."}'
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

## Optional Ollama

Install and run Ollama locally, then pull a model:

```bash
ollama pull llama3.1
ollama serve
```

The backend uses:

- `OLLAMA_BASE_URL`, default `http://localhost:11434`
- `OLLAMA_MODEL`, default `llama3.1`
- `OLLAMA_TIMEOUT`, default `8`

Without Ollama, the same endpoints continue to work with deterministic fallback responses.

## Basic Usage

1. Start the backend.
2. Start the frontend.
3. Write a post and click `Share`.
4. Click `Simulate comments`.
5. Click `Simulate replies` to add nested replies.

## API

- `GET /health`
- `POST /posts`
- `GET /posts`
- `GET /posts/{post_id}`
- `POST /posts/{post_id}/simulate`
- `POST /posts/{post_id}/simulate-reply`
