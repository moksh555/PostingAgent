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


## Stage 17 — A second prompt for regeneration

- Once the Accept / Reject interrupt loop was working, `Regenerate` needed
  its own prompt. The generation prompt was the wrong shape — it asks the
  model to produce a fresh post from the brief, but on regeneration we
  already have a draft and specific user feedback to apply.
- Built `app/prompts/postRegenerationPrompt.py::POST_REGENERATION_PROMPT` as
  a static system prompt (same "no placeholders" pattern as the generation
  prompt, for LangChain chaining).
- The key design decision: make the model **classify the scope of the user's
  feedback before rewriting**. Two buckets with six concrete examples each:
  - **Surgical edit** — "drop #LLMs", "fix the typo", "change CTA to point
    to pricing page". Prompt rule: keep every other sentence word-for-word,
    do not paraphrase, only change the targeted element.
  - **Structural rewrite** — "make it shorter", "switch to contrarian
    angle", "more casual tone". Full rewrite. Product names and brief-sourced
    stats may stay, but hook and body are re-authored.
- Tiebreaker: if scope is ambiguous, prefer surgical. Users who want a full
  rewrite usually say so explicitly.
- Other hard rules: the brief remains the single source of truth (no
  inventing facts even on regen), respect the brand AVOID list from the
  brief, no emojis unless the brief's tone section allows them.


## Stage 18 — Splitting generation into a two-node regen architecture

- Originally considered reusing `generatingMarketingPosts` for regeneration
  via a self-edge. Rejected:
  - A single node that sometimes generates and sometimes regenerates has to
    branch on state, switch prompts, and pass different inputs to the LLM.
    Messy.
  - A dedicated node lets each prompt stay focused and each code path stay
    linear.
- New graph shape:

  ```
  START
    → Validating_Payload
    → Building_Marketing_Brief
    → Drafting_And_Reviewing_Posts  ⇄  Regenerating_With_Feedback
                     │                          ↺
                     ↓
                    END
  ```

  - `Drafting_And_Reviewing_Posts` handles initial draft + review. Accept
    loops back for the next slot; Regenerate hands off to the regen node.
  - `Regenerating_With_Feedback` takes the rejected draft + user feedback,
    produces a rewrite, pauses for review. Accept / Reject → back to
    Drafting; Regenerate → self-loop for another rewrite.
- Four nodes total: `Validating_Payload`, `Building_Marketing_Brief`,
  `Drafting_And_Reviewing_Posts`, `Regenerating_With_Feedback`.


## Stage 19 — Draft caching to survive interrupt replay

This was the hardest bug of the project: **LangGraph replays nodes on
resume, it doesn't continue them from where they paused**.

- When `interrupt()` resolves via `Command(resume=...)`, LangGraph re-runs
  the whole node from the top. It caches each `interrupt()` call's resume
  value by *position in the node* — so on replay, the N-th `interrupt()`
  returns the stored answer instantly.
- Critically, LangGraph **does not** cache arbitrary function calls. LLM
  invocations re-run on every replay.
- Failure mode of a naive loop (`LLM → interrupt → LLM → interrupt → …`):
  - For N posts, N² LLM calls across all resumes.
  - Worse: each replay of a given iteration produces a **different** draft
    (LLMs are non-deterministic). The cached interrupt value says "Accept"
    for draft X, but on replay the new draft is X' — so X' lands in the
    final posts list, not the X the user actually approved. Silent data
    corruption.
- Fix: use the state dict as a cache and split each produce/review cycle
  into **two node invocations**, separated by a checkpoint:

  1. **Invocation A (produce)** — if `state["cacheDraft"]` is None, call
     the LLM, validate the output, return `{"cacheDraft": draft, ...}`.
     No `interrupt()` on this invocation.
  2. **Router** — sees there's more work to do, routes back to the same
     node.
  3. **Invocation B (review)** — `cacheDraft` is populated, skip the LLM
     branch entirely, call `interrupt(...)`, process the answer, clear
     the cache in the return.

- On resume, Invocation B is replayed — but Invocation B never touched the
  LLM in the first place (it only reads `cacheDraft`), so replay is cheap
  and the draft the user approved is exactly the draft that gets appended.
- Same pattern copied to `Regenerating_With_Feedback` so regeneration also
  runs the LLM exactly once per draft, regardless of replays.


## Stage 20 — State-driven iteration with `currentLoopStartNumber`

- First version had an in-memory `for` loop over `numberOfPosts` inside
  `generatingMarketingPosts`. Worked until the first Regenerate, at which
  point:
  - The node returned control to `Regenerating_With_Feedback`.
  - Regen finished, control came back to `Drafting_And_Reviewing_Posts`.
  - The local `postList = []` reset to empty, loop restarted, and the final
    return `{"posts": postList}` **overwrote** the previously-accepted
    posts in state with an empty list.
- Moved iteration into state:
  - `currentLoopStartNumber: int` tracks how many slots have been decided.
  - Every invocation starts with `postList = state.get("posts") or []`
    (load existing) instead of a fresh list.
  - Every Accept / Reject / Regenerate return increments
    `currentLoopStartNumber` and carries the updated `posts` list forward.
  - The node only performs one step per invocation — either a produce or a
    review — then returns. The router decides whether to come back.
- **Semantic trap I hit twice**: `currentLoopStartNumber` must mean "slots
  decided", **not** "drafts produced".
  - First attempt: incremented on both produce and decide → counter moved
    twice per post → graph ended at `N/2` posts.
  - Second attempt: incremented only on produce → counter moved ahead of
    reviews → graph ended with the last draft still sitting in cache,
    unreviewed.
  - Correct: increment only on Accept / Reject / Regenerate (the decisions
    that end a slot's cycle).


## Stage 21 — Retry counters and failure-flag state hygiene

- If the LLM returns empty / invalid content, the node writes
  `{"failedToBuildPostsatGeneration": True, "failedToBuildPostatGenerationNumber": count + 1}`
  and returns. The router retries while the count is < 3, and returns `END`
  once exhausted. Same for the regen side with `...atRegeneration`.
- Two subtle bugs here:
  1. **`None + 1`**. On the first failure the counter is `None` in state,
     because it was never initialised. Addressed by reading with
     `state.get("...", 0)` or `or 0` at every read site.
  2. **Stale failure flag never cleared.** When a retry succeeded, the
     node reset its local `failedFlag = False` and `count = 0` — but those
     locals never made it back to state because the subsequent returns
     didn't include the keys. The router then kept seeing
     `failedFlag=True` in state forever, and the `elif` structure of the
     router meant the failure branch **bypassed the "are we done yet?"
     progress check**. Result: after any transient failure, the graph
     could never exit cleanly — it either looped forever or terminated
     early depending on the counter state.
- Fix: every success-path return (post-LLM cache write, Accept, Reject,
  Regenerate) now explicitly carries
  `"failedToBuildPostsatGeneration": False` and
  `"failedToBuildPostatGenerationNumber": 0` into state. Same for the regen
  flags. The router's fail branch is now only live while a real failure
  exists.


## Stage 22 — Router design and conditional-edge gotchas

Things I learned the hard way about `add_conditional_edges`:

- **Only one `add_conditional_edges` per source node.** Early on I had
  two on `Drafting_And_Reviewing_Posts`: one for Regenerate-vs-END and
  another for retry-vs-END. The second call silently overwrote the first,
  so the Regenerate route never fired. Consolidated into a single routing
  function per source node that handles every transition.
- **A routing function returning `None` crashes the graph.** If a function
  falls off the end without a `return`, it returns `None`, which isn't a
  valid destination in LangGraph's edge mapping. Every branch must resolve
  to either `END` or a named node string. I hit this when I had
  `elif failed: if count < 3: return ...` with no `else` — the
  "retries exhausted" path returned `None`. Fixed by adding a terminal
  `return END` at the function level.
- **`None < int` raises `TypeError`.** State keys read via `state.get(...)`
  return `None` when unset. Comparisons like
  `state.get("currentLoopStartNumber") < numberOfPosts` blow up on the
  first run. Fixed everywhere with `(state.get("...") or 0)`.

Final gen-side router logic, in priority order:

1. `regeneratePost` truthy → `Regenerating_With_Feedback`
2. `failedToBuildPostsatGeneration` truthy:
   - retries left (`count < 3`) → same node (retry)
   - otherwise fall through to `END`
3. `currentLoopStartNumber < numberOfPosts` → same node (next slot)
4. Otherwise → `END`

Regen-side mirror:

1. `regeneratePost` falsy → `Drafting_And_Reviewing_Posts` (escape)
2. `failedToBuildPostsatRegeneration` + count ≥ 3 → `END`
3. Otherwise → same node (self-loop for chained regen, or waiting for
   review)


## Stage 23 — Graph visualisation helper

- Added `tests/graphGenerating.py` to dump the compiled graph as both a
  Mermaid string and a `graph.png`. Small but handy during the regen
  restructure — re-running it after each edit made wiring mistakes
  immediately obvious.
- Tricks the script pulls:
  - Stubs out `IPython.display` before importing the graph module, so
    LangGraph's `draw_mermaid_png` helpers don't `ModuleNotFoundError` in
    an environment without IPython.
  - Adds `Backend/` to `sys.path` so `app.*` and `configurations.*`
    resolve when running the script directly.
- Avoided installing Graphviz system-wide (the `pygraphviz` build pulls in
  C headers); LangGraph's Mermaid renderer covers the same ground with
  zero native deps.


## Stage 24 — Consolidating retries on LangGraph's `RetryPolicy`

Stage 21's hand-rolled retry machinery (`failedToBuildPostsatGeneration`,
`failedToBuildPostatGenerationNumber`, the mirror pair for regeneration,
plus the router's fail branch) was working but carried real cost:

- Two extra state keys per stage that every success-path return had to
  reset in lockstep.
- A router branch whose only job was "bypass the progress check if a
  stale flag was left dangling".
- No `sleep` / backoff between attempts — a transient 429 just got hit
  again immediately.

LangGraph already ships `RetryPolicy`, which retries a node **on
exception**, not on a flag. Swapped to that:

```python
workflow.add_node(
    "Drafting_And_Reviewing_Posts",
    generatingMarketingPosts,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on=[FailedToBuildPosts],
    ),
)
```

Refactor that followed:

- **Nodes now raise `FailedToBuildPosts`** on invalid LLM output instead
  of returning a failure flag. Both `generatingMarketingPosts` and
  `regeneratePost` mirror each other here.
- **`except FailedToBuildPosts: raise`** added *above* the generic
  `except Exception` block so retries don't double-wrap into
  `FailedToBuildPosts("Failed to build posts: Failed to build posts: ...")`.
  Same `GraphInterrupt` passthrough lesson from Stage 13, different
  exception.
- **Dropped** `failedToBuildPostsatGeneration`,
  `failedToBuildPostatGenerationNumber`, and the regen mirrors from
  `AgentState` entirely. Router lost its fail branch and went back to a
  clean three-case decision.
- `retry_on=[FailedToBuildPosts]` (list of exception classes) — important
  that this is the *class* that exhausted attempts raise to the caller,
  not a catch-all; anything else (e.g. a true `psycopg` error during
  checkpoint write) must not be silently retried.

Gotchas I hit during the swap:

- **`retry_delay=1`** isn't a valid `RetryPolicy` kwarg.
  `TypeError: RetryPolicy.__new__() got an unexpected keyword argument
  'retry_delay'`. Use `initial_interval` and/or `backoff_factor`.
- **Manual `node_attempt` guard cancels `RetryPolicy`.** Tried an early
  `if runtime.execution_info.node_attempt > 1: raise FailedToBuildPosts`
  thinking it would work *with* the retry policy. What it actually did
  was shortcut the second attempt — so `max_attempts=3` behaved like
  `max_attempts=1`. Either own the retry count yourself (no
  `RetryPolicy`), or let `RetryPolicy` own it (no manual guard). Not
  both.
- **`runtime.execution_info`** is a property, not a method. Earlier code
  had `runtime.get_execution_info()` which doesn't exist.


## Stage 25 — Testing under `pytest`

Wired up real test coverage once the retry story was stable:

- Added `pytest>=9.0.3` to the `dev` dependency group and
  `[tool.pytest.ini_options]` with `pythonpath = ["."]` and
  `testpaths = ["tests"]` so imports resolve from `Backend/`.
- `tests/conftest.py` provides three shared fixtures that every test
  leans on:
  - `noWritesToDisk` (autouse) — monkeypatches `writeSummaryToFile` so
    `buildingMarketingBrief` never touches the filesystem in tests.
  - `makeFakeLLM` — returns a factory that builds a `RunnableLambda`
    which pops responses off a queue and, when the queued value is an
    `Exception`, raises it. Lets a single test simulate "LLM returns
    valid output on attempt 3" without touching the Gemini API.
  - `newThreadConfig` — a fresh `{"configurable": {"thread_id": uuid}}`
    per test so threads never collide in the checkpointer.
- `os.environ.setdefault("GEMINI_API_KEY", "test-key-unused-because-we-mock")`
  at the top of `conftest.py` — `ChatGoogleGenerativeAI(...)` is
  instantiated at module import time in `agentGraph.py` and would
  otherwise fail during collection on a clean machine.

Test file `tests/test_agentGraph.py` covers ~18 cases across three
levels:

1. **Unit tests for pure functions** — `receiverNode`,
   `routingGneratePostsNode`, `routingReGneratePostsNode`. Fast, no LLM
   mocking needed.
2. **Single-node LLM tests** — `buildingMarketingBrief` (happy path +
   invalid-response raises), produce-step of
   `generatingMarketingPosts`, produce-step of `regeneratePost`. Uses
   `makeFakeLLM` to pin the response.
3. **End-to-end flow tests** — full run through `graph.invoke(...)` +
   `Command(resume=...)` for:
   - Happy path: 1-post Accept.
   - Regenerate flow: draft → Regenerate → rewrite → Accept.
   - Reject flow: draft → Reject → terminates with empty posts list.
   - **Replay safety** (`test_cacheDraftPreventsDoubleLLMCallOnResume`):
     asserts the LLM was called exactly once despite the node being
     replayed on resume. This is the regression test for Stage 19.
4. `InMemorySaver` inside tests — no Postgres required for CI. The
   module's own `PostgresSaver` lives under `if __name__ == "__main__":`
   precisely so tests can import `workflow` without a live DB.

One shell quirk worth recording: zsh swallows `#` as a comment when
typing `pytest tests/test_agentGraph.py # just the flow tests` at the
prompt and interprets the trailing `#` as a literal path. Either drop
the inline comment or `setopt interactive_comments` in `~/.zshrc`.


## Stage 26 — PostgreSQL checkpointer via Neon

`InMemorySaver` was fine for local dev but obviously can't survive a
process restart. Switched persistence to **Neon** (managed Postgres)
via LangGraph's `PostgresSaver`.

- Added `langgraph-checkpoint-postgres` — separate package from
  `langgraph` itself, pulls in `psycopg` and `psycopg-pool`.
- Added `POSTGRES_DB_URI` to the Pydantic-Settings config.
- Neon hands you a URI with `?sslmode=require` already appended; use
  the **direct** connection string (not the pooler) for `setup()` since
  it issues DDL.

Several false starts here that are worth recording, because the
documentation makes them easy to make:

1. **`PostgresStore` ≠ checkpointer.** First attempt was
   `checkpointer = PostgresStore(URI)`. `PostgresStore` is LangGraph's
   long-term *memory store* (for persistent key-value memory across
   threads), not a `BaseCheckpointSaver`. Wrong class, also not
   imported — `NameError` at module load.
2. **`PostgresSaver(URI)` — wrong constructor.** `PostgresSaver.__init__`
   requires a live `psycopg` connection (or pool) as its first
   positional arg. It does not parse URIs.
3. **`PostgresSaver.from_conn_string(URI)` without a `with`.** This
   classmethod is a `@contextmanager`. Assigning its result to a
   variable gives you a `_GeneratorContextManager`, not a saver.
   `checkpointer.setup()` on it raises `AttributeError`.
4. **`with … as checkpointer:` at module scope.** Correct shape, but
   the connection closes the instant the `with` block exits — which
   means any `graph.invoke(...)` *after* the block dies with
   `InterfaceError: the connection is closed`. Fine for a one-shot
   script if *all* usage lives inside the block; wrong for a long-lived
   FastAPI process.
5. **`from_conn_string(URI, serde=serde)`** doesn't accept a `serde`
   kwarg — `from_conn_string` always constructs the saver as
   `cls(conn)` internally, with no hook for a custom serializer.

Shapes that actually work:

- **One-shot script (what `__main__` uses today)**: stay inside the
  `with` block.

  ```python
  with PostgresSaver.from_conn_string(config.POSTGRES_DB_URI) as checkpointer:
      checkpointer.setup()
      graph = workflow.compile(checkpointer=checkpointer)
      # every graph.stream / graph.invoke call goes HERE
  ```

- **Long-running service (FastAPI, needs custom serde, or both)**: open
  the psycopg connection yourself and pass it to `PostgresSaver`.

  ```python
  import psycopg
  with psycopg.Connection.connect(
      config.POSTGRES_DB_URI,
      autocommit=True,
      prepare_threshold=0,
  ) as conn:
      checkpointer = PostgresSaver(conn, serde=serde)
      checkpointer.setup()
      graph = workflow.compile(checkpointer=checkpointer)
  ```

  `autocommit=True` and `prepare_threshold=0` are required — without
  them LangGraph's checkpoint writes occasionally hit
  `InFailedSqlTransaction`.

Also kept `setup()` as an idempotent no-op on subsequent runs — it
creates `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` on first
invocation and does nothing thereafter.


## Stage 27 — Thread inspection utility

Added `tests/inspectThread.py`: given a `thread_id` from Neon, prints
`posts`, `next`, and the full `posts` JSON dump.

```bash
uv run python tests/inspectThread.py <thread_id>
```

- Opens its own short-lived `PostgresSaver.from_conn_string(...)` and
  compiles the workflow with that checkpointer (doesn't need `setup()`
  — reads only).
- Uses `graph.get_state({"configurable": {"thread_id": threadId}})` —
  the blessed way to read a snapshot. Returns a `StateSnapshot` whose
  `.values` is the last persisted `AgentState` dict.
- `snapshot.next` tells you whether the thread is mid-interrupt
  (non-empty) or finished (empty tuple).
- Prepends `Backend/` to `sys.path` at the top of the script so
  `python tests/inspectThread.py` works directly, not just
  `python -m tests.inspectThread`. `pyproject.toml`'s
  `pythonpath = ["."]` applies to pytest only, not plain `python`.

Useful when the graph runs in a server and I need to inspect what a
given run produced without a UI. Also doubles as a debugging tool
during the serializer-allowlist work in Stage 28.


## Stage 28 — Checkpoint serializer allowlist

Running `inspectThread.py` against a real Neon thread printed a
warning for every Pydantic model in state:

```
Deserializing unregistered type app.models.AgentModels.AgentPost from
checkpoint. This will be blocked in a future version. Set
LANGGRAPH_STRICT_MSGPACK=true to block now, or add to
allowed_msgpack_modules to allow explicitly:
[('app.models.AgentModels', 'AgentPost')]
```

What's going on: LangGraph's default serde is
`JsonPlusSerializer` on top of msgpack. When it encounters a type it
doesn't recognise (i.e. our Pydantic models), it serialises a
`(module, class)` reference. On read-back it normally `import`s that
path to reconstruct the object — a real RCE surface if a checkpoint
row is ever tampered with. Future LangGraph releases will **block**
deserialisation of unknown types by default; right now they only warn.

Two live options:

- **(A) Store dicts in state, not Pydantic models.** Call
  `model_dump()` before handing an object to state, validate back with
  `Model.model_validate(...)` at read sites. Zero warnings, no coupling
  of checkpoints to Python module paths, survives renames and moves of
  the Pydantic classes.
- **(B) Register the types with the serializer.** Pass a custom
  `JsonPlusSerializer(allowed_msgpack_modules=[...])` to the saver.
  Keeps the typed objects in state but binds every existing checkpoint
  row to the current module + class names — rename `AgentModels.py`
  or a class and old threads stop deserialising.

For a project that's still small and evolving, **Option A is the safer
default**. Option B is staged in the `__main__` script for
experimentation but the plan is to migrate state to plain dicts
(`payload`, `posts`, `cacheDraft`, `postToRegenerate`) in a follow-up
pass.

Integration note specific to Option B: `PostgresSaver.from_conn_string`
won't forward a `serde` kwarg (Stage 26 bullet 5), so Option B
requires the manual `psycopg.Connection.connect(...)` pattern to get
`serde=` into the `PostgresSaver` constructor.


## Stage 29 — Service layer + client simulator

With the checkpointer working, the next layer up was the thing an HTTP
handler would actually call. Two methods, not one:

- `AgentServices.startRun(payload)` — mints a `thread_id`, compiles the
  graph against a fresh `PostgreSQLRepository()`, streams the run until
  it pauses on `interrupt(...)` or finishes, and returns a client view
  of the state.
- `AgentServices.resumeRun(thread_id, decision)` — same shape, but
  feeds `Command(resume=decision)` into `graph.stream(...)` instead of
  an initial payload.

Stream loop uses `stream_mode="updates"` with `version="v2"` and the
`chunk["type"] == "updates"` pattern — incremental node updates let me
log per-node progress for every run without blocking on a final
`invoke`. The return value is built by a small `_buildClientView(graph,
threadId, config)` helper that reads `graph.get_state(config)` and
folds `snapshot.next` + `values["cacheDraft"]` + `values["posts"]`
into one of two shapes:

- `{state: "awaiting_review", draft: {...}, posts: [...]}` when the
  thread is paused at an interrupt.
- `{state: "completed", draft: None, posts: [...]}` when the thread
  has reached `END`.

Same shape for `startRun` and `resumeRun` so the frontend doesn't need
two parsers. `posts` is always `[AgentPost.model_dump()]` so HTTP
serialisation is trivial.

HTTP wiring lives in `app/api/version1/runAgent.py`:

- `POST /runAgent` → `service.startRun(payload)`.
- `POST /runAgent/{thread_id}/decide` → `service.resumeRun(thread_id,
  decision)`.

`thread_id` lives in the path of the resume endpoint, not in a cookie
or header — a run is idempotent on its `thread_id` and the URL should
say so. (Open question still: let the frontend mint the UUID and send
it on `startRun`? Recommended pattern, not yet adopted.)

To drive this without a UI, added `tests/simulateRun.py`:

```bash
uv run python tests/simulateRun.py --url <url> --posts 3            # interactive
uv run python tests/simulateRun.py --url <url> --posts 3 --auto-accept
```

The simulator is a CLI that impersonates a browser: calls `startRun`,
prints each draft, prompts `A / R / G` from stdin, builds the
appropriate `AgentPostGenerationInterrupt`, calls `resumeRun`, loops
until `state == "completed"`. Useful as both a demo and a smoke test
against live Gemini + live Neon. `--auto-accept` mode lets it run
unattended for end-to-end regression checks.


## Stage 30 — Prompt ↔ schema mismatch caught by the simulator

First run through the simulator uncovered a bug that all the unit
tests missed (because they mock the LLM): for `numberOfPosts=3`,
post 1 came back as the string `"A single parseable JSON array of
objects representing the social media posts."` — literally the model
regurgitating a meta-description of what its output should be.
Subsequent drafts (regenerations, acceptances for later slots) worked
fine.

Root cause: `LLMPostGeneration` schema has exactly two fields —

```python
class LLMPostGeneration(BaseModel):
    content: str
    publishDate: datetime
```

…but `POST_GENERATION_PROMPT`'s `## Output` section asked for
**eight** (`angle`, `hook`, `body`, `cta`, `hashtags`, `publishDate`,
`platform`, `fullPost`) and referred to "the posts" (plural) while
the schema is a single object. `with_structured_output(...)` forces
output to match the schema, so every other field the prompt mentioned
was silently dropped, and since neither `content` nor `publishDate`
had a `Field(description=...)`, the model had no anchor for what to
put in `content`. For the first call of the run it improvised a
description of the schema; later calls stabilised on "dump the whole
hook+body+CTA+hashtags into `content` as one giant string".

This is literally the lesson already in this file ("Prompt ↔ schema
must agree") — the prompt just hadn't been updated when the schema
was shrunk.

Fixes, in order of impact:

1. **Descriptions on the schema fields** — `Field(..., description=
   "The full post as one string, with real newlines between
   paragraphs...")` on `content`, same for `publishDate`.
   `with_structured_output` passes these to the model. When the prompt
   contradicts the schema, the descriptions are what the model falls
   back to.
2. **Rewrite the prompt's `## Output` section** to describe the
   actual two-field schema (single object, `content` as assembled
   string, `publishDate` as ISO-8601). Drop the 8-field checklist
   entirely. Same edit in `postRegenerationPrompt.py` if it carries
   the same shape.
3. **Normalise literal `\n` in the node, defence-in-depth.** Same fix
   Stage 10 already applied to the marketing brief — Gemini
   double-escapes and emits the two characters `\` + `n` instead of a
   real newline. Post content was missing this step, so drafts
   printed as one giant line with visible `\n\n` separators. Two
   `.replace("\\n", "\n").replace("\\t", "\t")` calls on
   `postGenerated.content` right after the LLM call.
4. **Min-length guard.** Current validation only checks
   `content in ("", None)`. A one-liner schema description slipped
   through because it was a non-empty string. A
   `len(content.strip()) < 120` floor is a cheap sanity filter and
   activates `RetryPolicy` on schema-leak garbage.

Non-bug worth writing down: `numberOfPosts=3` → `2 post(s) accepted`
is **correct** per Stage 20 semantics. Reject = skip this slot; the
final list is shorter than `numberOfPosts` by whatever the user
rejected. If the UX ever wants "Reject retries the same slot", it's
a router change (don't increment `currentLoopStartNumber` on Reject).
Current call: keep Reject = skip, Regenerate-with-feedback is the
useful retry path.

Also a meta-lesson: unit tests with mocked LLMs would not catch this.
`simulateRun.py` against real Gemini is a necessary complement.


## Stage 31 — Streaming node updates to the client

`AgentServices.startRun` / `resumeRun` used to be plain functions that
called `graph.stream(...)` internally, drained the loop, and returned
the final `{state, draft, posts}` dict in one shot. That's fine for a
CLI — useless for a UI. A human-in-the-loop run can sit at an
`interrupt(...)` for minutes while the user reads the draft, and the
browser has nothing to show in the meantime.

Refactor: make the service methods **generators**.

- Yield per-node events as the graph streams:
  `yield json.dumps({"state": "updates", "node": node_name})`.
- `return` the final client view at the end — captured by the caller
  via `StopIteration.value`.
- HTTP layer in `app/api/version1/runAgent.py` wraps the generator in
  `StreamingResponse`, so the browser gets a live feed of node
  transitions over one long-lived response instead of polling.

Gotchas specific to "return a value from a generator":

- **`return <value>` inside a generator is legal** in Python 3, but the
  value isn't delivered through iteration — only through
  `StopIteration.value`. Callers that just did `for event in stream:
  ...` silently dropped the final view.
- **`simulateRun.py` had to be rewritten** around a `consumeRun` helper
  that does `while True: next(stream)` in a `try` / `except
  StopIteration as stop: finalPayload = stop.value` loop. It prints
  node events as they arrive and parses `stop.value` at the end.
- **`stream_mode="updates"` + `version="v2"` shape**: each chunk is
  `{"type": "updates", "data": {node_name: partial_state}}`. The
  service filters on `chunk["type"] == "updates"` and only forwards
  the node name; partial state leaks internal keys to the client, so
  it's intentionally dropped before `json.dumps`.
- **Single client-view helper**: `_buildClientView(graph, threadId,
  config)` stays unchanged from Stage 29. `startRun` and `resumeRun`
  both `return` its result at the end — the frontend gets the same
  shape regardless of which endpoint emitted it.


## Stage 32 — Prompt cleanup after the schema fix

Stage 30 traced the "schema-description-as-content" bug to a
`POST_GENERATION_PROMPT` that still asked for 8 output fields against
a 2-field schema. The minimum fix was a rewrite of the `## Output`
section, but the prompt had accumulated a lot of stale scaffolding
over two iterations (placeholder templating, platform-specific
conventions, scheduling rules, variety checklists, angle banks). Now
that variety and scheduling context are injected as a separate
`HumanMessage` at call time (`previousPostsSummary`, the `Publish date
for THIS post: ...` block), most of that scaffolding was double work.

Trimmed the prompt from ~130 lines to ~44. What's left:

- **Context** — one paragraph pointing at the brief as the single
  source of truth.
- **Task** — one paragraph saying "exactly one post per invocation,
  pick an unused angle".
- **Rules** — four bullets: draw facts from the brief, vary the angle,
  no AI stock phrases, no emojis unless the brief's tone section
  allows them.
- **Output** — two bullets, matching the two schema fields
  (`content`, `publishDate`). No preamble, no extra fields.

Everything that was genuinely per-call (post index, total posts,
campaign start date, platform, already-accepted posts) now lives in
the human-message payload the node assembles per invocation, not in
the system prompt. The system prompt stays constant across calls and
is easy to diff against the schema in one screenful.

Lesson already on the list ("prompt ↔ schema must agree"), corollary:
prompts that grew during exploration are liabilities once the schema
stabilises. Cut anything the schema no longer asks for.


## Stage 33 — Marketing brief persistence on S3

Up through Stage 10 the marketing brief was being written to local
disk under `Backend/testSummary/<slug>-brief.txt`. Fine for the
developer machine, obviously wrong for a service that runs in a
container, behind a load balancer, or on ephemeral instances where
`testSummary/` vanishes on restart. Moved brief storage to S3.

New pieces:

- **`app/repository/s3connection.py`** — a thin `S3Connection` wrapper
  around `boto3.client("s3", ...)` with `put_object(body, bucketName,
  key)` and `get_file(bucketName, key)` helpers. Construction reads
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`,
  `AWS_BUCKET_NAME` from `Config`. An `if __name__ == "__main__"`
  block round-trips a small object so `uv run python -m
  app.repository.s3connection` doubles as a credentials smoke test.
- **`configurations/config.py`** picked up the four AWS fields.
  `.env` gets the same four keys; `.env.example` stays gitignored but
  allow-listed.
- **`app/errorsHandler/errors.py`** grew a
  `FailedToWriteSummaryToS3(AppError)` so the brief-build path can
  distinguish "Gemini misbehaved" from "S3 credentials / bucket are
  broken". Same `AppError` plumbing — consistent JSON envelope for
  free.
- **`app/services/agentGraph.py::writeSummaryToS3(response)`**
  replaces the old `writeSummaryToFile`. Writes
  `response.marketingBrief` to `UserNotes/<response.fileName>` in the
  configured bucket. `buildingMarketingBrief` calls it right after
  validating the LLM output.
- **Exception ordering in `buildingMarketingBrief`** had to be
  extended by the same lesson from Stages 13 and 24: a new typed
  exception means a new passthrough branch before the catch-all,
  otherwise `except Exception` silently rewraps
  `FailedToWriteSummaryToS3` into `FailedToBuildMarketingBriefError`
  and the router picks the wrong retry behaviour.

  ```python
  except FailedToWriteSummaryToS3:
      raise
  except FailedToBuildMarketingBriefError:
      raise
  except Exception as e:
      raise FailedToBuildMarketingBriefError(...) from e
  ```

- **`boto3>=1.42.95`** added to `pyproject.toml`; `uv.lock` refreshed.

Not yet done (intentional, next stage):

- Using the S3 object URL as the input for downstream nodes instead
  of the in-memory `marketingNotes` string. That change lets the
  brief survive graph recompiles and lets a separate service (or a
  cold-started replica) regenerate posts without re-running the
  brief node.


## Stage 34 — `commands.py` runbook and `__init__.py` slim-down

Two small chores that had been piling up:

- **`Backend/commands.py`** — a single documented reference for every
  runnable entrypoint in the project: `main.py` (FastAPI via
  `uv run fastapi dev main.py` or `uvicorn main:app --reload`),
  `app/repository/s3connection.py` (as `python -m
  app.repository.s3connection`), every script under `tests/` (both
  `python -m` and `python <path>` forms, since the test scripts
  prepend `Backend/` to `sys.path` themselves), and the pytest /
  uv housekeeping commands. Also explicitly lists which files are
  *not* runnable directly (pure library modules under `services/`,
  `api/`, `models/`, `prompts/`, `errorsHandler/`,
  `configurations/`) so future-me doesn't go looking for a
  `__main__` that never existed. Running `uv run python commands.py`
  prints the whole thing as a cheat sheet.

- **`app/errorsHandler/__init__.py` emptied.** The old file
  re-exported every error class at the package root
  (`from app.errorsHandler import AppError, NoURLError, ...`).
  It had already drifted: `FailedToBuildPosts` was listed without
  quotes inside `__all__` (so `__all__` contained the class, not the
  string), and every new error class (e.g.
  `FailedToWriteSummaryToS3`) needed two edits — one in `errors.py`,
  one in `__init__.py` — or the package-level import stopped
  working. Call sites were mixed anyway. Cleaned up by deleting the
  re-exports; everything now imports from
  `app.errorsHandler.errors` explicitly. Less magic, one source of
  truth, no `__all__` to keep in sync.


## Stage 35 — Dependency modules and breaking the import cycle

The stack hit a **circular import** once `app.services.agentGraph`
imported `get_postgres_repository` (or equivalent) from a module that
also imported `AgentServices`, while `AgentServices` imports
`workflow` from `agentGraph`. Python then failed with *partially
initialized module* errors at startup.

**Fix — separate concerns and keep graph imports acyclic:**

- **`app/api/depends/repositoryDepends.py`** — two `@lru_cache(maxsize=1)`
  factories, each returning a `PostgreSQLRepository`:
  - `get_postgres_repository_checkpointer()` — its `ConnectionPool`
    backs `PostgresSaver` for LangGraph checkpoints (wired in
    `AgentServices.__init__` via `PostgresSaver(self.conn, serde=SERDE)`
    and `repository.setup(self.checkpointer)`).
  - `get_postgres_repository_posts()` — used only from
    `saveDataToDatabase` in `agentGraph.py` for
    `saveFinalPostDataExecuteMany` into the `posts` table.

  This module imports **only** `PostgreSQLRepository` from
  `app.repository.postgreSQL` — no `AgentServices`, no `agentGraph` —
  so it is safe for `agentGraph` to import from it.

- **`app/api/depends/servicesDepends.py`** — `get_agent_services()`
  returns a cached `AgentServices()` (no repository argument; the
  service pulls the checkpointer repo internally). FastAPI routes import
  this, not `AgentServices` directly.

**Trade-off:** two cached factories means **two** `PostgreSQLRepository`
instances and thus **two** connection pools to the same Neon URI
unless later collapsed to a single shared `get_postgres_repository()`.
That was accepted for clarity between checkpoint I/O and app-table
inserts; it is **not** required for import hygiene — a single pool would
also work if all code paths shared one `repository.conn`.

**API wiring:** `POST /api/v1/runAgent` uses
`StreamingResponse(get_agent_services().startRun(payload=...))` so the
client receives streamed node-update JSON lines plus the final client
view via the generator contract described in Stage 31.


## What the system does end-to-end today

1. Client `POST /api/v1/runAgent` with `{userId, url, numberOfPosts, startDate}`.
2. FastAPI validates the body → `AgentRunRequest`.
3. `get_agent_services().startRun(payload)` streams the compiled LangGraph
   with a stable `thread_id` so the checkpointer can pause / resume across
   interrupts; the HTTP layer returns a `StreamingResponse` over that
   generator.
4. **Validating_Payload** — sanity-checks the payload (redundant with the
   FastAPI boundary, useful for direct-invocation tests).
5. **Building_Marketing_Brief** — Gemini produces the structured
   `AgentSummary`; the node returns it in state as **`notes`**
   (downstream post generation reads `notes.marketingBrief`). The brief
   body is also uploaded with `writeSummaryToS3` to
   `s3://<AWS_BUCKET_NAME>/UserNotes/.../fileName` via `S3Connection`.
   S3 write failures → `FailedToWriteSummaryToS3`; include
   `AgentSummary` in `JsonPlusSerializer(allowed_msgpack_modules=[...])`
   so checkpoint resume does not turn `notes` into an opaque `dict`
   (see Stage 28).
6. **Drafting_And_Reviewing_Posts** — state machine; one step per
   invocation:
   - **Produce step** (cache miss): chain the generation prompt with
     `LLMPostGeneration` structured output, validate, write draft to
     `cacheDraft`, return. Router loops back for the review step.
   - **Review step** (cache hit): `interrupt(...)` pauses with
     `{postContent, publishDate, actions: [Accept, Reject, Regenerate]}`.
7. Client resumes (e.g. from `tests/simulateRun.py` or a future
   `/runAgent/.../decide` route) via
   `Command(resume=AgentPostGenerationInterrupt(...))`:
   - **Accept** — append `AgentPost`, clear `cacheDraft`, increment
     `currentLoopStartNumber`, reset failure flags. Router loops back if
     more posts are needed; otherwise routes to `Saving_Data_To_Database`
     when the campaign is complete.
   - **Reject** — clear `cacheDraft`, increment
     `currentLoopStartNumber`, reset failure flags. (Reject = skip this
     slot; delivers fewer posts than requested.)
   - **Regenerate** — set `regeneratePost: True`, stash the draft in
     `postToRegenerate`, send `postChangeDescription` along. Router hands
     off to `Regenerating_With_Feedback`.
8. **Regenerating_With_Feedback** — same produce/review state machine but
   with `POST_REGENERATION_PROMPT` and access to the previous draft +
   user feedback. Accept / Reject → back to
   `Drafting_And_Reviewing_Posts`; Regenerate self-loops for another
   rewrite.
9. Consecutive LLM failures on produce-steps raise `FailedToBuildPosts`;
   LangGraph's `RetryPolicy(max_attempts=3, backoff_factor=3,
   retry_on=[FailedToBuildPosts])` retries the node. If all three
   attempts exhaust, the exception bubbles up to the caller rather than
   silently landing an empty slot.
10. Every checkpoint is persisted to **Neon Postgres** via
    `PostgresSaver` (pooled through the checkpointer-side repository from
    Stage 35), so a run paused at `interrupt(...)` survives a
    process restart and can be resumed hours later using the same
    `thread_id`.
11. **Saving_Data_To_Database** — final node: `writeSummaryToS3` for
    notes, then `get_postgres_repository_posts()`.
    `saveFinalPostDataExecuteMany(...)` into the `posts` table
    (Neon, same URI, separate connection pool from the checkpointer
    in the current two-factory design).
12. The service layer surfaces accepted posts as JSON (see
    `_buildClientView`); the HTTP stream ends with the completed client
    view when the graph reaches `END`.


## Lessons worth keeping

- **Dependency direction kills circular imports.** A graph module
  must not import a package that eventually imports the graph (e.g.
  `from app.api.depends import X` if `depends` loads `AgentServices` →
  `agentGraph`). Keep DB singletons in **leaf** modules
  (`app.repository.*` or `repositoryDepends` that import only
  `PostgreSQLRepository`) and have `agentGraph` import from there;
  use `servicesDepends` at the FastAPI boundary for `get_agent_services`.
- **Let the framework validate at the boundary.** Pydantic at FastAPI +
  `extra="forbid"` makes "bad request" cases free.
- **Custom exceptions pay for themselves** as soon as you need consistent
  error envelopes and log filtering.
- **LangGraph interrupts are just exceptions** under the hood — any
  `try/except Exception` in a node will silently break pause/resume unless
  you passthrough `GraphInterrupt` explicitly.
- **LangGraph replays nodes, it doesn't resume them.** Every interrupt
  resume re-runs the node from the top. Anything that must not run twice
  (LLM calls, paid side effects, non-deterministic work) has to be cached
  in state and guarded on replay.
- **State mutations must travel via node returns.** Updating a Python
  local doesn't persist — the checkpointer only sees what a node returns.
  If you want to clear a flag, return `{"flag": False}`; don't just
  reassign the local.
- **Increment counters on decide, not on produce.** A slot is "done" when
  the user Accepts / Rejects / Regenerates, not when the LLM has produced
  a draft. Getting this wrong ends the graph one cycle early or late.
- **State keys compared to numbers need defaults.** Either seed them in an
  upstream node or `or 0` them at every read site. `None < int` is a hard
  crash.
- **One `add_conditional_edges` per source node.** Multiple calls
  overwrite; a single router function must handle every transition.
  Routers that fall off the end (return `None`) crash the graph — every
  branch needs a terminal.
- **Two prompts for two tasks.** Reusing a generation prompt for
  regeneration means the model keeps producing from-scratch posts instead
  of targeted rewrites. Distinct prompts, distinct node, distinct inputs.
- **Surgical vs structural is a real UX distinction.** A regen prompt that
  always rewrites everything feels aggressive when the user only asked to
  drop a hashtag. Teach the model to classify scope before acting.
- **Structured output and long-form output fight each other.** Keep the
  long body plain-text with a continuation loop; use structured output
  only for the fields you actually need to parse.
- **Prompt ↔ schema must agree.** If the prompt asks for 8 fields but the
  schema has 2, the schema wins and the prompt's instructions get ignored.
- **`python -m` is the right way to run a module** inside a package —
  don't run the file directly.
- **Exception-driven retries beat flag-driven retries.** If the
  framework ships a retry primitive (`RetryPolicy`), use it: raise a
  typed exception on failure, let the policy own `max_attempts` and
  backoff, and delete the mirroring state keys. Don't mix the two —
  manual `node_attempt` guards silently cancel out `RetryPolicy`.
- **Checkpointer lifecycle is the whole game with `PostgresSaver`.**
  `from_conn_string` is a context manager that closes on `__exit__`;
  `PostgresSaver(conn, serde=...)` wants a connection you own.
  Anything that mixes the two (`postgres = PostgresSaver(serde=...)`
  then `postgres.from_conn_string(...)`) is wrong in a subtle way
  because `from_conn_string` is a classmethod and discards the
  instance. Pick the shape that matches the process lifetime.
- **Pydantic models in LangGraph state are a forward-compat footgun.**
  Default serde warns today, will block tomorrow. Plain dicts in
  state + `Model.model_validate(...)` at read sites is the lower-risk
  path unless you deliberately want the registry coupling.
- **Neon requires SSL and autocommit.** `?sslmode=require` in the URI
  plus `autocommit=True, prepare_threshold=0` when constructing the
  connection. Without `autocommit`, checkpoint writes sometimes land
  in `InFailedSqlTransaction`.
- **Tests must not need the database.** Keeping
  `PostgresSaver` construction under `if __name__ == "__main__":` (or
  behind a `buildGraph(checkpointer)` factory) lets
  `tests/conftest.py` import the workflow without a live Neon
  instance. The corollary: `graph` should not be a module-level
  Postgres-backed global, ever.
- **`Field(description=...)` is the schema's last word.** When a
  prompt and a structured-output schema disagree, the schema wins and
  the model reads the field descriptions for intent. Un-described
  fields give the model nothing to hold onto, and it will hallucinate
  schema-shaped garbage (e.g. emitting the schema description as the
  field value). Every field that isn't obvious from its name needs a
  description.
- **Mocked-LLM tests cannot catch prompt regressions.** They validate
  graph topology and node contracts, not model behaviour. A real-LLM
  smoke script (`simulateRun.py`) on every prompt change is cheap
  insurance for the class of bugs that only appear when the actual
  model has to make a decision.
- **Stream with `stream_mode="updates"` + `version="v2"`.**
  Incremental per-node deltas, not final state. Pairs with
  `chunk["type"] == "updates"` parsing. `.invoke(...)` blocks on the
  whole run; `stream(...)` lets the service layer log each node as it
  runs and exit cleanly on the first `interrupt(...)`.
- **One client-view shape for start and resume.** The frontend should
  not need to know whether this is the first call or the fifth.
  `{state, draft, posts}` derived from `graph.get_state(config)` is
  the same whether the thread just paused for the first time or
  resumed from `Command(resume=...)`. Build it in one helper
  (`_buildClientView`) and call it from both service methods.
- **Generators that `return` hide their final value.** A service
  method that streams node events *and* produces a terminal view has
  to be consumed with a `try: next(...) / except StopIteration as
  stop: stop.value` pattern, not a plain `for` loop. If you're
  plugging the generator into `StreamingResponse`, split the two
  responsibilities (stream *or* return-the-view), or document the
  `StopIteration.value` contract loudly — otherwise callers silently
  drop the final state.
- **Persist artefacts off the local filesystem.** Brief-to-disk was
  convenient until the service needed to run outside the dev
  machine. S3 (or any object store) + a thin wrapper that owns
  credentials via `Config` beats `Path(__file__).parent / ...`. Pair
  it with a dedicated exception class (`FailedToWriteSummaryToS3`)
  so storage failures don't get miscategorised as LLM failures and
  routed through `RetryPolicy`. Every new typed exception needs its
  own passthrough branch above the catch-all in the node that uses
  it — same rule as `GraphInterrupt` and `FailedToBuildPosts`.
- **Package `__init__.py` as API, not as re-export boilerplate.**
  A big re-export block that has to be edited in lockstep with every
  new class in the package will drift. If call sites are importing
  from the submodule directly anyway, delete the re-exports and keep
  `__init__.py` empty (or minimal). One source of truth beats a
  second one that silently falls out of sync.
