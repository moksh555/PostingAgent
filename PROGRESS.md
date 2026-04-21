# Marketing Agent — Build Progress

A running log of how this project was built, in the order it actually happened.
Each milestone includes the *why* behind the decision, the main files touched,
and any errors that shaped the design.


## Stage 0 — Environment & tooling

- Chose **`uv`** as the package manager + runner. Faster than `pip`, gives a
  reproducible `uv.lock`, and lets me run modules with `uv run python -m ...`.
- Python **3.10** pinned via `.python-version`.
- Project layout:

  ```
  Backend/
    app/
      api/          # FastAPI routers
      errorsHandler/# custom exception types
      models/       # Pydantic schemas
      prompts/      # LLM prompts
      services/    # LangGraph workflow + business logic
    configurations/ # Pydantic-Settings config, .env
    main.py         # FastAPI app entrypoint
    testSummary/    # generated marketing briefs (gitignored)
  ```

- `pyproject.toml` + `uv sync` handles the dependency tree.


## Stage 1 — FastAPI skeleton

- Created `main.py` with a titled FastAPI app (`title="Marketing Agent API"`,
  `version="1.0.0:v1"`) — the title is not optional: an empty title triggers
  `AssertionError: A title must be provided for OpenAPI`.
- Wired a main `APIRouter` at `app/api/router.py` that mounts versioned
  sub-routers under `/api/v1`.
- First working endpoint: **`GET /api/v1/healthChecks/live`** returning a
  Pydantic `HealthCheckModel`. That gave me something to hit with curl to
  confirm the server boots and import paths are wired correctly.


## Stage 2 — Request / response contract

- Defined Pydantic models in `app/models/AgentModels.py`:
  - `AgentRunRequest` — `url`, `numberOfPosts` (1-9), `startDate` (ISO-8601).
    Used `model_config = ConfigDict(extra="forbid")` so unknown fields → 422.
    Used `pattern=` (NOT `regex=`, which is removed in Pydantic v2) for the
    URL regex.
  - `AgentRunResponse` — status/message/echo of inputs.
- Decided to let **FastAPI + Pydantic handle request-layer validation
  automatically**: empty body, missing fields, wrong types, and out-of-range
  `numberOfPosts` all become 422 without extra code.


## Stage 3 — Custom error system

- Created `app/errorsHandler/errors.py` with an `AppError` base class that
  carries `status_code`, `code`, and `message`. Concrete subclasses:
  - `NoPayloadError` (400)
  - `NoURLError`, `NoNumberOfPostsError`, `NoStartDateError` (400)
  - `FailedToScrapeURLError` (500)
  - `FailedToBuildMarketingBriefError` (500)
  - `FailedToBuildPosts` (500)
- Registered a global exception handler for `AppError` in `main.py` so every
  error returns the same `{"status", "code", "message"}` envelope.
- Also added a `RequestValidationError` handler for consistent 422 envelopes.


## Stage 4 — Wiring the `/runAgent` endpoint

- `app/api/version1/runAgent.py` now accepts a typed `payload: AgentRunRequest`
  and delegates to `AgentServices.runAgent(...)`.
- Exception mapping inside the route:
  - `ValueError`              → 400
  - `TimeoutError`            → 504
  - `ConnectionError`         → 502
  - Pydantic `ValidationError` → 500 (this is an internal bug, not a client
    problem — the request already passed validation at the boundary)
  - catch-all `Exception`     → 500
- `AgentServices` initially returned a stub response so I could integration-test
  the HTTP layer before plugging in the real agent.


## Stage 5 — Configuration & secrets

- `configurations/config.py` uses `pydantic_settings.BaseSettings` to load a
  local `.env`:
  - `PORT`
  - `GEMINI_API_KEY`
- `.env` is gitignored. `configurations/.env` is also gitignored (belt &
  braces). An `.env.example` slot is allow-listed for later.
- Hit a classic Pydantic-Settings gotcha: if the field is named
  `GOOGLE_API_KEY` but the `.env` has `GEMINI_API_KEY`, Settings will raise
  `Field required`. Reconciled the two names.


## Stage 6 — LangGraph scaffold

- Picked **LangGraph** (over a plain orchestration script) because I knew I'd
  want: typed state, checkpointing, and human-in-the-loop interrupts.
- Created `AgentState(TypedDict)` with `payload`, `marketingNotes`, and
  `posts`. Each node returns a partial state dict that LangGraph merges.
- Graph shape settled at:

  ```
  START → receiver → buildingMarketingBrief → generatingMarketingPosts → END
  ```

- Attached an `InMemorySaver` checkpointer so the graph can pause at
  `interrupt(...)` and resume later with the same `thread_id`.


## Stage 7 — The first node: `receiverNode`

- Validates the payload and forwards it. Redundant with Pydantic validation at
  the FastAPI boundary, but useful when the graph is invoked directly (tests,
  scripts) without the HTTP layer.
- Early bugs I learned from:
  - `state["payload"]` vs `state.get("payload")` — `.get` is safer because
    LangGraph may pass a partial state.
  - `payload.get("url")` — wrong, `payload` is a Pydantic model not a dict.
    Attribute access: `payload.url`.


## Stage 8 — Marketing brief generation (`buildingMarketingBrief`)

- Picked **`ChatGoogleGenerativeAI`** (`gemini-3-flash-preview`). Important:
  `GoogleGenerativeAI` doesn't support structured output — only
  `ChatGoogleGenerativeAI` does.
- `LLM.with_structured_output(AgentSummary)` forces the model to return
  `{marketingBrief, fileName}`.
- Wrote `app/prompts/detailedDescription.py::MARKETING_BRIEF_PROMPT` — a
  12-section brief (positioning, ICP, value props, differentiators, tone,
  social proof, 10+ angle ideas, hashtags, constraints, open questions).
  Designed as the **single source of truth** for downstream post generation.
- Filename is generated deterministically from the URL via
  `_slugify_url_to_filename(url)`; keeps the `testSummary/` folder clean.


## Stage 9 — Continuation loop for long-form generation

- Problem: Gemini sometimes hits `max_output_tokens` mid-brief and truncates.
- Solution: `_generateFullBrief(initial_prompt)` runs a loop that:
  1. Invokes a plain-text LLM (not structured) with the full prompt.
  2. Checks `finish_reason`. If `STOP` / sentinel `<<END_OF_BRIEF>>` present →
     done.
  3. Otherwise: re-invokes asking "continue exactly where you left off,
     don't repeat" and stitches the chunks.
  4. Safety cap of `MAX_BRIEF_ITERATIONS = 8` so a stuck model can't loop
     forever.
- Trade-off: plain-text output for the brief body, structured output only
  for the filename. Two calls, but reliable length.


## Stage 10 — Writing the brief to disk

- `writeSummaryToFile(response)` lives at
  `<project>/testSummary/<slug>-brief.txt`.
- Found that Gemini's structured output sometimes **double-escapes** `\n`
  and `\t` (they arrive as literal `\\n`). Added string replacements to
  normalise before writing.


## Stage 11 — Post generation prompt

- `app/prompts/postGenerationprompt.py::POST_GENERATION_PROMPT`. A full
  copywriting brief with:
  - Hard rules (no AI stock phrases, draw every fact from the brief,
    respect the tone section).
  - Structure per post: hook, body, CTA, hashtags.
  - Platform conventions for LinkedIn / Twitter / Instagram.
  - Scheduling rules (one post/day, skip weekends for B2B, default 09:30
    local).
  - A variety checklist (no two posts share the same angle, hashtag overlap
    ≤ 40%).
- Evolved through two iterations:
  1. First draft had `{url}`, `{start_date}`, `{platform}`, `{brief}` as
     template placeholders.
  2. Refactored to a **static system prompt** — no placeholders — because I
     wanted to attach the brief + scheduling info via LangChain chaining as
     a separate `HumanMessage`. Cleaner separation of instructions vs.
     context, and fewer brace-escaping issues if the brief contains `{` or
     `}`.


## Stage 12 — Post generation node (`generatingMarketingPosts`)

- Uses `ChatPromptTemplate.from_messages([("system", ...), ("human", ...)])`
  chained with a structured-output LLM bound to `LLMPostGeneration`.
- Iterates `numberOfPosts` times, and after each LLM call pauses the graph
  via `interrupt(...)` so the user can Accept / Reject / Regenerate.


## Stage 13 — Human-in-the-loop with `interrupt`

Most instructive stage. Several bugs in a row taught me how LangGraph
actually pauses:

1. **`interrupt()` raises internally.** It works by raising
   `GraphInterrupt`. The graph runtime catches it, checkpoints, and returns.
   My generic `try/except Exception` was catching it first and re-wrapping
   it as `FailedToBuildPosts`, so the graph never paused — it errored.

   Fix: add an explicit passthrough *above* the catch-all:

   ```python
   except GraphInterrupt:
       raise
   except Exception as e:
       raise FailedToBuildPosts(...) from e
   ```

2. **Resume payload type mismatch.** `interrupt()` returns whatever was
   passed to `Command(resume=...)`. Passing `"Accept"` (a string) and then
   accessing `answer.actions` → `AttributeError`.

   Fix: pass a Pydantic `AgentPostGenerationInterrupt` object on resume, or
   compare the string directly in the node. Chose the Pydantic path for
   future-proofing (once there's a `postChangeDescription` field too).

3. **Thread ID stability.** The same `thread_id` must be used on the
   original `invoke` and the `Command(resume=...)` invoke — that's how the
   checkpointer finds the paused run.

4. **`Field(..., default="", ...)` is a TypeError.** In Pydantic v2, the
   first positional arg *is* the default; `...` is the sentinel for
   "required". Can't combine them. Fix:
   `postChangeDescription: str = Field(default="", description="...")`.


## Stage 14 — Git & `.gitignore`

- Initialised the Backend as its own git repo with a remote to GitHub.
- Wrote a comprehensive `.gitignore` covering:
  - Secrets (`.env`, `configurations/.env`, with allow-list for `.env.example`)
  - Python bytecode / caches
  - Virtualenvs
  - Linter / type-checker caches (`.ruff_cache`, `.mypy_cache`, etc.)
  - IDE folders (`.vscode/`, `.idea/`, `.cursor/`)
  - `testSummary/` (runtime artefacts, not source)
- Kept `uv.lock` tracked — reproducible installs.


## Stage 15 — Running the module correctly

- `python agentGraph.py` fails because it puts `app/services/` on `sys.path`,
  not the project root, so `configurations.*` can't be found.
- `python app/services/agentGraph.py` has the same problem.
- Correct invocation from `Backend/`:

  ```bash
  uv run python -m app.services.agentGraph
  ```

  `python -m` puts the cwd (`Backend/`) on `sys.path`, so both `app.*` and
  `configurations.*` resolve.


## Stage 16 — Observability (planned)

Shortlist for the next iteration:
- Replace `print(...)` with Python `logging` for timestamped, level-aware
  logs.
- Switch `graph.invoke()` → `graph.stream(stream_mode="updates")` to see
  each node boundary in real time.
- Add **LangSmith** tracing (`LANGSMITH_TRACING=true`) for a proper waterfall
  of node / LLM / token / interrupt events.


## What the system does end-to-end today

1. Client `POST /api/v1/runAgent` with `{url, numberOfPosts, startDate}`.
2. FastAPI validates the body → `AgentRunRequest`.
3. `AgentServices.runAgent` compiles and invokes the LangGraph.
4. **receiverNode** — sanity-checks the payload.
5. **buildingMarketingBrief** — calls Gemini in a continuation loop,
   produces a 12-section brief, writes it to `testSummary/<slug>.txt`.
6. **generatingMarketingPosts** — for each of `numberOfPosts`:
   - Chains the post-generation prompt with `LLMPostGeneration` structured
     output.
   - `interrupt(...)` pauses the graph with
     `{postContent, publishDate, actions: [Accept, Reject, Regenerate]}`.
   - Client resumes with a decision; Accept appends the post, Regenerate
     loops back on the same slot.
7. Returns `posts: list[AgentPost]`.


## Lessons worth keeping

- **Let the framework validate at the boundary.** Pydantic at FastAPI +
  `extra="forbid"` makes "bad request" cases free.
- **Custom exceptions pay for themselves** as soon as you need consistent
  error envelopes and log filtering.
- **LangGraph interrupts are just exceptions** under the hood — any
  `try/except Exception` in a node will silently break pause/resume unless
  you passthrough `GraphInterrupt` explicitly.
- **Structured output and long-form output fight each other.** Keep the
  long body plain-text with a continuation loop; use structured output only
  for the fields you actually need to parse.
- **Prompt ↔ schema must agree.** If the prompt asks for 8 fields but the
  schema has 2, the schema wins and the prompt's instructions get ignored.
- **`python -m` is the right way to run a module** inside a package — don't
  run the file directly.
