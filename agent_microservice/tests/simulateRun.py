"""
Simulate a frontend driving the HITL agent loop end-to-end.

Exercises the real `AgentServices` so this doubles as an integration
test of the service layer:
    service.startRun → [awaiting_review → service.resumeRun]* → completed

`startRun` / `resumeRun` are generators: they yield JSON strings per
node update during `graph.stream(...)` and `return` a JSON-serialized
client view at the end (captured via StopIteration.value). This
simulator drains the generator, prints per-node progress, and parses
the final view.

Usage:
    uv run python tests/simulateRun.py
    uv run python tests/simulateRun.py --auto-accept
    uv run python tests/simulateRun.py --posts 2 --url https://example.com
    uv run python tests/simulateRun.py --posts 1 --userId local-dev-user
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.AgentModels import (
    AgentPostGenerationInterrupt,
    AgentRunRequest,
)
from app.services.AgentServices import AgentServices


SEP = "=" * 70


def consumeRun(stream: Generator[str, None, Any]) -> dict[str, Any]:
    """
    Drain a startRun / resumeRun generator.

    - Prints each yielded node-update event.
    - Returns the parsed final client view dict, captured from
      StopIteration.value (i.e. the generator's `return` payload).
    """
    finalPayload: Any = None
    try:
        while True:
            event = next(stream)
            try:
                parsed = json.loads(event)
            except (TypeError, json.JSONDecodeError):
                print(f"  · raw: {event}")
                continue

            node = parsed.get("node")
            if node:
                print(f"  · node: {node}")
            else:
                print(f"  · event: {parsed}")
    except StopIteration as stop:
        finalPayload = stop.value

    if finalPayload is None:
        raise RuntimeError(
            "Run generator completed without returning a client view. "
            "Expected AgentServices to `return _buildClientView(...)` "
            "at the end of the stream."
        )

    if isinstance(finalPayload, str):
        return json.loads(finalPayload)
    if isinstance(finalPayload, dict):
        return finalPayload
    raise RuntimeError(f"Unexpected final payload type: {type(finalPayload)!r}")


def printDraft(draft: dict) -> None:
    print(f"\n{SEP}")
    print(f"DRAFT FOR REVIEW  (publishDate: {draft['publishDate']})")
    print("-" * 70)
    print(draft["content"])
    print(SEP)


def promptDecision() -> AgentPostGenerationInterrupt:
    while True:
        raw = input("\nAction [A=Accept / R=Reject / G=Regenerate]: ").strip().lower()
        if raw in ("a", "accept"):
            return AgentPostGenerationInterrupt(actions="Accept")
        if raw in ("r", "reject"):
            return AgentPostGenerationInterrupt(actions="Reject")
        if raw in ("g", "regenerate"):
            feedback = input("What should change? ").strip()
            return AgentPostGenerationInterrupt(
                actions="Regenerate",
                postChangeDescription=feedback or "please rewrite",
            )
        print("invalid choice; try again")


def simulate(autoAccept: bool, url: str, numberOfPosts: int, userId: str) -> None:
    service = AgentServices(get_postgres_repository())

    print(f"\nurl:    {url}")
    print(f"posts:  {numberOfPosts}")
    print(f"mode:   {'AUTO-ACCEPT' if autoAccept else 'INTERACTIVE'}")

    payload = AgentRunRequest(
        url=url,
        numberOfPosts=numberOfPosts,
        startDate=datetime.now(timezone.utc),
        userId=userId,
    )

    print("\ncalling service.startRun(...)")
    view = consumeRun(service.startRun(payload))
    threadId = view["threadId"]
    print(f"\nthread_id: {threadId}")
    print(f"state:     {view['state']}")

    while view["state"] == "awaiting_review":
        if view["draft"] is None:
            print("graph paused but no draft in state — exiting")
            return

        printDraft(view["draft"])

        if autoAccept:
            decision = AgentPostGenerationInterrupt(actions="Accept")
            print("[auto-accept]")
        else:
            decision = promptDecision()

        print(f"\ncalling service.resumeRun(action={decision.actions})")
        view = consumeRun(service.resumeRun(threadId, decision))
        print(f"state:     {view['state']}")

    print(f"\n{'#' * 70}")
    print(f"COMPLETED — {len(view['posts'])} post(s) accepted")
    print(f"thread_id: {threadId}")
    print("#" * 70)

    for i, post in enumerate(view["posts"], start=1):
        print(f"\nPost {i} (publishDate: {post['publishDate']}):")
        print("-" * 70)
        print(post["content"])


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--auto-accept",
        action="store_true",
        help="Accept every draft without prompting (good for smoke tests)",
    )
    parser.add_argument(
        "--url",
        default="https://code.claude.com/docs/en/agent-sdk/overview",
    )
    parser.add_argument("--posts", type=int, default=1, help="numberOfPosts (1-9)")
    parser.add_argument(
        "--userId",
        type=str,
        default="test_user",
        help="user id (required by AgentRunRequest; default is for local smoke tests)",
    )
    args = parser.parse_args()

    simulate(
        autoAccept=args.auto_accept,
        url=args.url,
        numberOfPosts=args.posts,
        userId=args.userId,
    )
