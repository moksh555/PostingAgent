import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore

from app.services.agentGraph import workflow
from configurations.config import config


def inspectThread(threadId: str) -> None:
    with PostgresSaver.from_conn_string(config.POSTGRES_DB_URI) as checkpointer:
        graph = workflow.compile(checkpointer=checkpointer)

        snapshot = graph.get_state({"configurable": {"thread_id": threadId}})

        if snapshot is None or not snapshot.values:
            print(f"No state found for thread_id={threadId}")
            return

        posts = snapshot.values.get("posts") or []

        print(f"thread_id: {threadId}")
        print(f"next nodes: {snapshot.next}")
        print(f"posts count: {len(posts)}")

        for i, post in enumerate(posts, start=1):
            data = post.model_dump() if hasattr(post, "model_dump") else post
            print(f"\n--- post {i} ---")
            print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: uv run python tests/inspectThread.py <thread_id>")
        sys.exit(1)
    inspectThread(sys.argv[1])
