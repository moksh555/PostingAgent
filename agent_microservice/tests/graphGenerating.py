"""Render the LangGraph workflow as Mermaid (and optional PNG).

Uses the same ``StateGraph`` as production: ``app.services.agentGraph.workflow``,
compiled **without** a checkpointer (graph shape matches
``workflow.compile(checkpointer=...)`` in ``AgentServices.create``).

Always writes a ``.mmd`` file next to the optional PNG path. PNG uses LangChain’s
Mermaid render (default: mermaid.ink) and is skipped on failure (e.g. offline, proxy).

Run from ``Backend/``:

    uv run python -m tests.graphGenerating
    uv run python tests/graphGenerating.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_backend_on_path() -> Path:
    backend_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_dir))
    return backend_dir


def generateGraphArtifacts(output_png: Path | None = None) -> Path:
    """Build Mermaid from the current ``workflow``; write ``.mmd``; try ``.png``."""
    backend_dir = _ensure_backend_on_path()

    from app.services.agentGraph import workflow  # noqa: WPS433

    graph = workflow.compile()
    graph_view = graph.get_graph()
    mermaid_text = graph_view.draw_mermaid()
    print(mermaid_text)

    if output_png is None:
        output_png = Path(__file__).resolve().parent / "graph.png"
    output_mmd = output_png.with_suffix(".mmd")
    output_mmd.write_text(mermaid_text, encoding="utf-8")
    print(f"\nwrote {output_mmd.relative_to(backend_dir)}")

    try:
        graph_view.draw_mermaid_png(
            output_file_path=str(output_png),
            max_retries=3,
            retry_delay=2.0,
        )
        print(f"wrote {output_png.relative_to(backend_dir)}")
    except Exception as exc:
        print(
            f"\nPNG skipped ({type(exc).__name__}: {exc!s})",
            file=sys.stderr,
        )
        print(
            "Mermaid source is in the .mmd file. For PNG, allow outbound HTTPS to "
            "mermaid.ink or use a Mermaid/Graphviz local renderer on that file.",
            file=sys.stderr,
        )

    return output_mmd


if __name__ == "__main__":
    generateGraphArtifacts()
