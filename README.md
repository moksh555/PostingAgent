# Backend — Marketing / Posting Agent

This folder holds the **Python microservices** for the Posting Agent product: an AI-assisted workflow that ingests product documentation, drafts social posts, supports **human-in-the-loop** review, and (in the full vision) schedules publishing.

The **Vite frontend** lives in a separate repository (`PostingAgent-FrontEnd`); it talks to these APIs over HTTP with CORS + cookies where configured.

---

## What’s in this repo (today)

| Service | Role | Stack (high level) |
|--------|------|---------------------|
| **`authentication_microservice`** | Users: register, login, refresh, session from cookies | FastAPI, async PostgreSQL (`asyncpg`), JWT + refresh tokens, Argon2 hashing |
| **`agent_microservice`** | Run/resume the marketing agent, threads, snapshots | FastAPI, LangChain / LangGraph, Gemini, PostgreSQL checkpoints, S3 (`aioboto3`) |
| **`posting_microservice`** | **Scaffold only** — package layout and placeholder `main`; not wired as a full API yet | FastAPI + boto3 declared in `pyproject`; structure mirrors `authentication_microservice` |

Each service is meant to be run **from its own directory** with its own virtualenv and `configurations/.env` (see below).

---

## `authentication_microservice`

**Purpose:** Issue and validate auth tokens, persist users, expose health and identity for the SPA.

**App entry:** `main.py` — FastAPI app with lifespan hook to open/close the DB pool (`PostgreSQLRepository`).

**API prefix:** `/userservices/v1`

| Area | Routes (version1) |
|------|-------------------|
| Health | Health check |
| Auth | Login, register, refresh |
| Session | `getUserFromToken` (cookie-based access + refresh flow) |

**CORS:** Allows local Vite dev origins (`localhost` / `127.0.0.1` on common Vite ports) with credentials.

**Configuration:** `configurations/config.py` reads `configurations/.env`:

- `AUTHENTICATION_SECRET_KEY`, `AUTHENTICATION_ALGORITHM`, `AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES`
- `AUTHENTICATION_REFRESH_SECRET_KEY`, `AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS`
- `POSTGRES_DB_URI`
- `VERSION`

**Layout:** `app/` (api → `depends`, `version1`, models, services, repository, `errorsHandler`), `configurations/`, `tests/`.

---

## `agent_microservice`

**Purpose:** Orchestrate the **marketing agent graph** (documentation → drafts → HITL-style flow), persist thread state, and integrate with object storage.

**App entry:** `main.py` — FastAPI + global `AppError` handler + CORS (same style as auth for local frontends).

**API prefixes:** Mostly `/agentservices/v1` and **also** some routers under `/agentServices/v1` (mixed casing in code — treat as distinct paths when calling from clients).

| Area | Routes (version1) |
|------|-------------------|
| Health | Health check |
| Agent | Start agent, resume agent, user thread states, thread snapshot |

**Configuration:** `configurations/.env` typically includes:

- `PORT`, `GEMINI_API_KEY`, `POSTGRES_DB_URI`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `AWS_BUCKET_NAME`

**Layout:** `app/` (api, services including graph, tools, prompts, models, repository, errors), `configurations/`, `tests/` (including graph tests and helpers).

**More detail:** See `agent_microservice/README.md` for product narrative, stack (LangGraph, Neon/S3, Lambda/EventBridge goals), and MVP direction.

---

## `posting_microservice`

**Purpose (planned):** Dedicated service for **posting / scheduling** concerns (e.g. glue to Lambda, EventBridge, or platform APIs).

**Today:** Folder structure aligned with `authentication_microservice` (`app/`, `configurations/`, `tests/` with package `__init__.py` files). `main.py` is a minimal placeholder (`Hello from posting-microservice!`). No shared router with production endpoints yet.

---

## Running locally

**Requirements:** Python **≥ 3.11**, PostgreSQL (and AWS/Gemini credentials for the agent service as needed).

1. Create a virtualenv in the service directory (or use `uv` / your usual tool).
2. Install deps: e.g. `pip install -e .` from that service’s root (see its `pyproject.toml`).
3. Add `configurations/.env` with the variables listed above for that service.
4. Start the API (exact command depends on your setup; commonly `fastapi dev main:app` or `uvicorn main:app --reload` from the service root).

Run **auth** and **agent** on **different ports** so both can be used alongside the frontend (which uses env vars such as `VITE_AUTH_BASE_URL` and agent base URL).

---

## Related documentation

- **Agent product & vision:** `agent_microservice/README.md`
- **Frontend:** separate repo; consumes `/userservices/v1/*` and agent endpoints according to its `ApiClient` / service modules

---

## Contributing / layout conventions

- **`app/api/version1/`** — FastAPI routers for the current API version  
- **`app/api/depends/`** — Dependency-injected helpers (e.g. auth dependencies in the auth service)  
- **`configurations/`** — Settings (`config.py`) and local `.env` (not committed if you add it to `.gitignore`)  
- **`errorsHandler` / `errors`** — Service-specific HTTP error types and handlers  

This README reflects the backend **as of the current tree**; extend it when `posting_microservice` gains real endpoints or shared deployment docs.
