# Authentication microservice — progress log

Working notes for the **PostingAgent** repo, service root: `authentication_microservice/`.  
Run the app from this folder: `uv run fastapi dev main.py` → `http://127.0.0.1:8000/docs`.

---

## Stack

- **Python ≥ 3.11**, **FastAPI** (with `[standard]` extras for CLI / dev server)
- **Pydantic v2** + **`pydantic[email]`** / **email-validator**
- **PyJWT** for access tokens, **pwdlib[argon2]** for password hashing
- **`pydantic-settings`** for env-backed config (`configurations/config.py`)
- **asyncpg** + **`PostgreSQLRepository`** connection pool (Neon-compatible Postgres DSN)

---

## Layout (high level)

| Area | Purpose |
|------|--------|
| `main.py` | FastAPI app, CORS, global exception handlers, **lifespan** (DB pool connect/disconnect, `app.state.db`) |
| `configurations/` | `Config` + `.env` (secret, JWT algorithm, token TTL, version, **`POSTGRES_DB_URI`**) |
| `app/api/version1/` | HTTP routes: health, login, register |
| `app/api/depends/` | **`auth.py`**: `get_postgres`, **`get_authentication_service`** for route DI |
| `app/models/` | Pydantic request/response and domain models |
| `app/services/` | **`AuthenticationService(db)`**, **`UserService(db)`** |
| `app/errorsHandler/` | Typed HTTP errors + per-domain base classes (**`databaseError`**, **`userError`**) |
| `app/repository/` | **`postgreSql.py`** (pool + `fetch` / `fetchrow` / `execute`), **`userRepository.py`** (users table) |
| `tests/` | Scaffold only |

---

## API (v1)

Routers are mounted under **`/userservices/v1`**:

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/userservices/v1/healthChecks/live` | Liveness probe |
| `POST` | `/userservices/v1/login` | Body: `LoginRequest` → JWT; **DB** email lookup + password verify; unknown email / bad password → `NotAuthorized` |
| `POST` | `/userservices/v1/register` | Body: `RegisterRequest` → persists user + JWT (**`sub`** + **`email`** in claims); refresh field still empty |

Paths are **not** under `/api/...` unless you add another prefix in `main.py`.

---

## Configuration

- **`configurations/config.py`**: `BaseSettings` with `model_config = SettingsConfigDict(...)` loading **`configurations/.env`**.
- Expected env: `VERSION`, `AUTHENTICATION_SECRET_KEY`, `AUTHENTICATION_ALGORITHM`, `AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES`, **`POSTGRES_DB_URI`** (asyncpg DSN, e.g. Neon with `sslmode=require`).
- **Operations:** use a strong `AUTHENTICATION_SECRET_KEY` (e.g. ≥ 32 bytes for HS256) to avoid PyJWT insecure-key warnings. **Do not commit `.env`** with real secrets.

---

## Error model

- **`AuthenticationError`** (`baseError.py`): app-wide root; `status_code`, `code`, `message`; JSON handler in `main.py`.
- **Domain bases** (each module defines a base + concrete errors, with docstrings):
  - **`LoginError`** → `NoEmailorPasswordFound`, `NotAuthorized`
  - **`RegisterError`** → **`RegisterPayloadError`** (422-style register payload / business rules)
  - **`TokenError`** → **`CredentialException`**
- **User / DB:** **`NoUserIdError`**, **`NoEmailError`**; repository failures → **`FailedTo*`** in `databaseError.py`.
- **`RequestValidationError`**: 422 with `code: payload_error` and Pydantic `details`.

---

## Models (summary)

- **Login:** `LoginRequest`, `LoginResponse` (`access_token`, `refresh_token`)
- **Register:** `RegisterRequest` (email, password, DOB, names, phone), `RegisterResponse`
- **User:** **`UserModel`** (public profile fields including `subscriptionType`); **`CreateUserModel`** (insert payload, includes password hash); **`UserPrivateModel`** (extends sensitivity for login — includes **`passwordHash`**)
- **Token:** **`TokenModel`** (JWT claims: **`sub`**, **`email`**), `Token` (`accessToken`, `tokenType`)

---

## Data layer

- **`PostgreSQLRepository`**: asyncpg pool; **`connect`** / **`disconnect`**; **`fetchrow`**, **`execute`**, etc., with domain **`FailedTo*`** wrappers.
- **`UserRepository`**: `getUserFromUserId`, `getUserFromEmail` (returns public + private models), `createUser` (returns **`UserModel`**, not the row with password). SQL uses **`$1`…** placeholders (asyncpg). UUID columns are read as **`uuid.UUID`** and mapped to **`str`** for `sub`.

---

## Services

### `UserService(db)`

- **`validateUserRegisterPayload`:** rules beyond Pydantic — `email-validator`, password complexity, names, phone, DOB age bounds.
- **`createUser`:** hashes password, builds **`CreateUserModel`**, **`UserRepository.createUser`**, returns **`UserModel`**.
- **`getUserFromUserId` / `getUserFromEmail`:** delegate to repository (`private=True` returns **`UserPrivateModel`** for login).
- **`comparePassword`:** **`pwdlib`** verify against stored hash.

### `AuthenticationService(db)`

- **`registerUser`:** validation + **`createUser`**, JWT encodes **`TokenModel(sub=…, email=…)`**.
- **`loginUser` / `authenticateUser`:** normalize email, load user with **`passwordHash`**, **`comparePassword`**; **`NoEmailError`** mapped to **`NotAuthorized`** (same message as bad password).
- **`encodeAccessToken`**, **`_decode_token_sub`**, **`decodeAccessToken`:** sign/verify; **`decodeAccessToken`** loads full **`UserModel`** via **`getUserFromUserId`** (for future protected routes).

---

## Cross-cutting

- **CORS** for local Vite ports (`5173` / `5174`).
- **Dependencies:** `pyproject.toml` / `uv.lock`. Prefer **`uv run`** so the project venv (including **anyio**, **pydantic**, etc.) stays consistent.
- **Local scripts:** avoid multiple **`asyncio.run`** calls around the same asyncpg pool (single async `main` per process).

---

## Done vs TODO

**In place:**

- App shell, CORS, auth + payload exception handlers
- Health, login, register routes with **FastAPI Depends** wiring to **`AuthenticationService(app.state.db)`**
- **Postgres pool** lifecycle in **`main.py` lifespan**
- JWT access tokens with **`sub` + `email`**; registration validation; **persisted users**; **login** verifies password against DB
- **`UserRepository`** + typed errors; **`decodeAccessToken`** → **`UserModel`**

**Next:**

- Refresh tokens; align **`OAuth2PasswordBearer(tokenUrl=...)`** with a real token route if clients use OAuth2 password flow
- Map DB **unique email** violations to a dedicated **`RegisterError`** (friendly duplicate-email message)
- Tests, CI, Alembic/migrations checked into repo (schema documented or migrated)

---

## Log

- **2026-05:** Scaffold documented; `Progress.md` created summarizing structure, endpoints, services, and open work.
- **2026-05 (update):** Documented **asyncpg**, **`UserRepository`**, **lifespan** / **`app.state.db`**, **Depends** in login/register, **real register + login**, **`TokenModel` email claim**, and revised TODOs.
