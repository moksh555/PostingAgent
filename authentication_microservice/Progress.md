# Authentication microservice — progress log

Working notes for the **PostingAgent** repo, service root: `authentication_microservice/`.  
Run the app from this folder: `uv run fastapi dev main.py` → `http://127.0.0.1:8000/docs`.

---

## Stack

- **Python ≥ 3.11**, **FastAPI** (with `[standard]` extras for CLI / dev server)
- **Pydantic v2** + **`pydantic[email]`** / **email-validator**
- **PyJWT** for access tokens, **pwdlib[argon2]** for password hashing
- **`pydantic-settings`** for env-backed config (`configurations/config.py`)

---

## Layout (high level)

| Area | Purpose |
|------|--------|
| `main.py` | FastAPI app, CORS, global exception handlers |
| `configurations/` | `Config` + `.env` (secret, JWT algorithm, token TTL, version) |
| `app/api/version1/` | HTTP routes: health, login, register |
| `app/models/` | Pydantic request/response and domain models |
| `app/services/` | `AuthenticationService`, `UserService` |
| `app/errorsHandler/` | Typed HTTP errors + per-domain base classes |
| `app/repository/` | Placeholder for future DB access |
| `tests/` | Scaffold only |

---

## API (v1)

Routers are mounted under **`/userservices/v1`**:

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/userservices/v1/healthChecks/live` | Liveness probe |
| `POST` | `/userservices/v1/login` | Body: `LoginRequest` → `LoginResponse` (access + refresh fields; refresh TODO) |
| `POST` | `/userservices/v1/register` | Body: `RegisterRequest` → `RegisterResponse` (access + empty refresh for now) |

Paths are **not** under `/api/...` unless you add another prefix in `main.py`.

---

## Configuration

- **`configurations/config.py`**: `BaseSettings` with `model_config = SettingsConfigDict(...)` loading **`configurations/.env`**.
- Expected env: `VERSION`, `AUTHENTICATION_SECRET_KEY`, `AUTHENTICATION_ALGORITHM`, `AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES`.
- **Operations:** use a strong `AUTHENTICATION_SECRET_KEY` (e.g. ≥ 32 bytes for HS256) to avoid PyJWT insecure-key warnings.

---

## Error model

- **`AuthenticationError`** (`baseError.py`): app-wide root; `status_code`, `code`, `message`; JSON handler in `main.py`.
- **Domain bases** (each module defines a base + concrete errors, with docstrings):
  - **`LoginError`** → `NoEmailorPasswordFound`, `NotAuthorized`
  - **`RegisterError`** → **`RegisterPayloadError`** (422-style register payload / business rules)
  - **`TokenError`** → **`CredentialException`**
- **`RequestValidationError`**: 422 with `code: payload_error` and Pydantic `details`.

---

## Models (summary)

- **Login:** `LoginRequest`, `LoginResponse` (`access_token`, `refresh_token`)
- **Register:** `RegisterRequest` (email, password, DOB, names, phone), `RegisterResponse`
- **User:** `UserModel` (`email`, `sub`, `userFirstName`, `userLastName`)
- **Token:** `TokenModel` (JWT claims), `Token` (`accessToken`, `tokenType`)

---

## Services

### `UserService`

- **`validateUserRegisterPayload`:** rules beyond Pydantic — `email-validator`, password complexity (length, upper/lower/digit/special), names, phone, DOB age bounds.
- **`createUser`:** Argon2 hash via **`PasswordHash.recommended()`**, builds a dict shaped for a future INSERT; returns **`UserModel`** with placeholder **`sub`** (`uuid4`) until the DB returns a real id.

### `AuthenticationService`

- **`loginUser` / `authenticateUser`:** credential path (DB check **TODO**); issues JWT.
- **`registerUser`:** validation + **`createUser`**, JWT with **`sub=user.sub`**.
- **`encodeAccessToken`**, **`_decode_token_sub`**, **`decodeAccessToken`:** sign/verify; decode loads user via **`getUserFromUserId`** (**TODO:** returns `None` today → 401 until DB).

---

## Cross-cutting

- **CORS** for local Vite ports (`5173` / `5174`).
- **Dependencies:** `pyproject.toml` / `uv.lock`.

---

## Done vs TODO

**In place:**

- App shell, CORS, auth + payload exception handlers
- Health, login, register routes
- JWT access tokens, registration validation, password hashing, stub user creation
- Layered error types with HTTP metadata

**Next:**

- DB schema, repository, real `createUser` / `getUserFromUserId` / login verify
- Refresh tokens; align `OAuth2PasswordBearer(tokenUrl=...)` with a real token route
- DI for services, tests, CI

---

## Log

- **2026-05:** Scaffold documented; `Progress.md` created summarizing structure, endpoints, services, and open work.
