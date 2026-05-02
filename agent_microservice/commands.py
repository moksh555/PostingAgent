"""
commands.py

Reference of all commands to run the runnable files in the agent microservice.

Run every command from the `Backend/agent_microservice/` directory, e.g.:
    cd /Users/moksh/Desktop/MarketingAgent/Backend/agent_microservice

This project is managed with `uv`, so the canonical invocation is
`uv run python ...`. If you have your own virtualenv activated, you can
drop the `uv run` prefix and just use `python ...`.

Notes on imports:
- Files that do `from configurations.config import ...` or `from app...`
  must be executed with `Backend/agent_microservice/` as the working directory, either as a
  module (`python -m ...`) or as a script (`python path/to/file.py`) when
  the script itself adds that directory to `sys.path` (the files under `tests/`
  already do this).
- Files that are purely library modules (no `if __name__ == "__main__"`
  block and used only as imports) are listed under NON-EXECUTABLE below
  — running them directly does nothing useful.
"""

# =============================================================================
# 1. FastAPI application (main entrypoint)
# =============================================================================
# Starts the HTTP server defined in main.py (app = FastAPI(...)).
#
#   uv run fastapi dev main.py                      # dev server with reload
#   uv run fastapi run main.py                      # production server
#   uv run uvicorn main:app --reload --port 8000    # alternative via uvicorn


# =============================================================================
# 2. Repository layer
# =============================================================================
# app/repository/s3connection.py
#   Has an `if __name__ == "__main__"` block that uploads graph.png (repo root of this service)
#   to S3. Needs AWS_* env vars from configurations/.env.
#
#   uv run python -m app.repository.s3connection
#
# app/repository/postgreSQL.py
#   Library module (no __main__ block). Imported by other files; not run
#   directly.


# =============================================================================
# 3. Services
# =============================================================================
# These are library modules and are exercised via main.py or the tests/
# scripts below. Running them directly is not meaningful.
#
#   app/services/AgentServices.py
#   app/services/agentGraph.py


# =============================================================================
# 4. API routes
# =============================================================================
# Library modules wired into main.py via app/api/router.py. Not run directly.
#
#   app/api/router.py
#   app/api/version1/healthCheck.py
#   app/api/version1/runAgent.py


# =============================================================================
# 5. Models / prompts / error handlers / config
# =============================================================================
# Pure library modules. Imported, never executed directly.
#
#   app/models/AgentModels.py
#   app/models/healthCheckModel.py
#   app/prompts/detailedDescription.py
#   app/prompts/postGenerationPrompt.py
#   app/prompts/postRegenerationPrompt.py
#   app/errorsHandler/errors.py
#   configurations/config.py


# =============================================================================
# 6. Test / utility scripts under tests/
# =============================================================================
# Each of these scripts prepends this service root to sys.path, so they can be
# invoked either as a module or as a plain script — both forms are shown.
#
# tests/simulateRun.py
#   End-to-end HITL simulator against AgentServices.
#
#   uv run python -m tests.simulateRun
#   uv run python tests/simulateRun.py
#   uv run python tests/simulateRun.py --auto-accept
#   uv run python tests/simulateRun.py --posts 2 --url https://example.com
#
# tests/inspectThread.py
#   Inspect a persisted LangGraph thread by id (reads POSTGRES_DB_URI).
#
#   uv run python -m tests.inspectThread <thread_id>
#   uv run python tests/inspectThread.py <thread_id>
#
# tests/graphGenerating.py
#   Print the compiled graph as Mermaid and write tests/graph.png.
#
#   uv run python -m tests.graphGenerating
#   uv run python tests/graphGenerating.py
#
# tests/test_agentGraph.py
#   Pytest suite for the agent graph (uses tests/conftest.py).
#
#   uv run pytest tests/test_agentGraph.py
#   uv run pytest tests/test_agentGraph.py -v
#   uv run pytest                                   # run everything


# =============================================================================
# 7. Dependency / project management (uv)
# =============================================================================
#   uv sync                      # install deps from pyproject.toml + uv.lock
#   uv add <package>             # add a new dependency
#   uv remove <package>          # remove a dependency
#   uv run python <anything>     # run any python command inside the env
#   uv lock                      # refresh uv.lock

if __name__ == "__main__":
    print(__doc__)
