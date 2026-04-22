"""Render the compiled LangGraph as Mermaid text + a PNG.

Run from the Backend/ directory:

    uv run python -m tests.graphGenerating
    # or
    uv run python tests/graphGenerating.py

Outputs:
    - prints the Mermaid flowchart source to stdout
    - writes <repo>/Backend/tests/graph.png

The script fakes the `IPython.display` module before importing the agent graph,
because agentGraph.py has a top-level `from IPython.display import Image, display`
that we don't want to force into the project's dependencies. If you remove that
import from agentGraph.py, you can delete the stub block below.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _stubIPython() -> None:
    """Register a no-op `IPython.display` module so agentGraph imports cleanly."""
    if "IPython.display" in sys.modules:
        return
    fake_display = types.ModuleType("IPython.display")
    fake_display.Image = lambda *a, **kw: None        # type: ignore[attr-defined]
    fake_display.display = lambda *a, **kw: None       # type: ignore[attr-defined]
    sys.modules.setdefault("IPython", types.ModuleType("IPython"))
    sys.modules["IPython.display"] = fake_display


def _ensureBackendOnPath() -> Path:
    """Make sure `app`, `configurations`, etc. are importable regardless of cwd."""
    backend_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_dir))
    return backend_dir


def generateGraphArtifacts(output_png: Path | None = None) -> Path:
    """Import the compiled graph, print its Mermaid source, save a PNG.

    Returns the path to the written PNG.
    """
    _stubIPython()
    backend_dir = _ensureBackendOnPath()

    # Import only after the stub + path are set up.
    from app.services.agentGraph import graph  # noqa: WPS433 (local import is intentional)

    mermaid_text = graph.get_graph().draw_mermaid()
    print(mermaid_text)

    if output_png is None:
        output_png = Path(__file__).resolve().parent / "graph.png"

    graph.get_graph().draw_mermaid_png(output_file_path=str(output_png))
    print(f"\nwrote {output_png.relative_to(backend_dir)}")
    return output_png


if __name__ == "__main__":
    generateGraphArtifacts()
