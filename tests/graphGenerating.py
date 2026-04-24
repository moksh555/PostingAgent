"""Render the compiled LangGraph as Mermaid + PNG, using the same `graph` as `AgentServices`.

Run from `Backend/`:

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
    backend_dir = _ensure_backend_on_path()

    from app.services.AgentServices import AgentServices  # noqa: WPS433

    graph = AgentServices().graph

    mermaid_text = graph.get_graph().draw_mermaid()
    print(mermaid_text)

    if output_png is None:
        output_png = Path(__file__).resolve().parent / "graph.png"

    graph.get_graph().draw_mermaid_png(output_file_path=str(output_png))
    print(f"\nwrote {output_png.relative_to(backend_dir)}")
    return output_png


if __name__ == "__main__":
    generateGraphArtifacts()
