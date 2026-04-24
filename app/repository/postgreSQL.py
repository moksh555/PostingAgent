from psycopg_pool import ConnectionPool  # type: ignore
from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
from app.services.agentGraph import workflow
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # type: ignore
from configurations.config import config
from datetime import datetime
import uuid
from langgraph.types import interrupt, RetryPolicy, Command  # type: ignore
from app.models.AgentModels import (
    AgentRunRequest,
    AgentPostGenerationInterrupt,
)


class PostgreSQLRepository:
    SERDE = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.models.AgentModels", "AgentRunRequest"),
            ("app.models.AgentModels", "LLMPostGeneration"),
            ("app.models.AgentModels", "AgentPost"),
        ],
    )

    def __init__(self):
        self.conn = ConnectionPool(
            config.POSTGRES_DB_URI,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        self.checkpointer = PostgresSaver(self.conn, serde=self.SERDE)
        self.checkpointer.setup()
        self.graph = workflow.compile(checkpointer=self.checkpointer)

    def get_graph(self):
        return self.graph

    def setup(self):
        self.checkpointer.setup()


if __name__ == "__main__":
    repository = PostgreSQLRepository()
    graph = repository.get_graph()
    configuration = {"configurable": {"thread_id": str(uuid.uuid4())}}
    for chunk in graph.stream(
        {
            "payload": AgentRunRequest(
                url="https://code.claude.com/docs/en/agent-sdk/overview",
                numberOfPosts=1,
                startDate=datetime.now(),
            )
        },
        config=configuration,
        version="v2",
    ):
        if chunk["type"] == "updates":
            for node_name, state in chunk["data"].items():
                print(f"Node {node_name}")
                if node_name == "__interrupt__":
                    answer = AgentPostGenerationInterrupt(actions="Accept")
                    graph.invoke(
                        Command(resume=answer), config=configuration, version="v2"
                    )
