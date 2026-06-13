# Architecture Notes

This MVP is intentionally small:

- `backend/` exposes a FastAPI REST API backed by SQLite.
- `frontend/` is a React + Vite app that calls the local API.
- Persona definitions live in `backend/personas.py`.
- Simulation lives in `backend/simulator.py`.
- Ollama is optional. If the local Ollama-compatible API is not available, deterministic template responses are returned.

The SQLite database is created automatically at `backend/friend_chat.db` when the backend starts.
