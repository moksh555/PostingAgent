from psycopg_pool import ConnectionPool  # type: ignore
from configurations.config import config
from datetime import datetime
from langgraph.checkpoint.postgres import PostgresSaver # type: ignore
from app.errorsHandler.errors import FailedToSaveFinalPostData


class PostgreSQLRepository:
    def __init__(self):
        self.conn = ConnectionPool(
            config.POSTGRES_DB_URI,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )

    def setup(self, checkpointer: PostgresSaver):
        checkpointer.setup()
    
    def saveFinalPostDataExecuteMany(self, data: list[tuple[str, str, str, str, datetime, str, datetime, str]]):
        try:
            with self.conn.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO posts (user_id, source_url, platform, content, publish_date, thread_id, created_at, notes_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        data,
                    )
        except Exception as e:
            raise FailedToSaveFinalPostData(f"Failed to save final post data: {e}") from e
