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


## What the system does end-to-end today

1. Client `POST /api/v1/runAgent` with `{url, numberOfPosts, startDate}`.
2. FastAPI validates the body → `AgentRunRequest`.
3. `AgentServices.runAgent` compiles and invokes the LangGraph with a
   stable `thread_id` so the checkpointer can pause / resume across
   interrupts.
4. **Validating_Payload** — sanity-checks the payload (redundant with the
   FastAPI boundary, useful for direct-invocation tests).
5. **Building_Marketing_Brief** — Gemini in a continuation loop produces
   a 12-section brief; `writeSummaryToFile` persists it under
   `testSummary/<slug>.txt`.
6. **Drafting_And_Reviewing_Posts** — state machine; one step per
   invocation:
   - **Produce step** (cache miss): chain the generation prompt with
     `LLMPostGeneration` structured output, validate, write draft to
     `cacheDraft`, return. Router loops back for the review step.
   - **Review step** (cache hit): `interrupt(...)` pauses with
     `{postContent, publishDate, actions: [Accept, Reject, Regenerate]}`.
7. Client resumes via `Command(resume=AgentPostGenerationInterrupt(...))`:
   - **Accept** — append `AgentPost`, clear `cacheDraft`, increment
     `currentLoopStartNumber`, reset failure flags. Router loops back if
     more posts are needed; otherwise `END`.
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
9. Consecutive LLM failures are retried up to 3 times per stage; beyond
   that the graph terminates cleanly at `END`.
10. Returns `posts: list[AgentPost]`.


## Lessons worth keeping

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
