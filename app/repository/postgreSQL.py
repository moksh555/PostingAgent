from datetime import datetime
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
from psycopg_pool import AsyncConnectionPool  # type: ignore

from configurations.config import config

from app.errorsHandler.errors import FailedToSaveFinalPostData


class PostgreSQLRepository:
    def __init__(self):
        self.conn = None
    
    @classmethod
    async def create(cls):
        instance = cls()
        instance.conn = AsyncConnectionPool(
            config.POSTGRES_DB_URI,
            min_size=1,
            max_size=10, 
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await instance.conn.open()
        return instance

    async def setup(self, checkpointer: AsyncPostgresSaver):
        await checkpointer.setup()
    
    async def saveFinalPostDataExecuteMany(self, data: list[tuple[str, str, str, str, datetime, str, datetime, str]]):
        try:
            async with self.conn.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        "INSERT INTO posts (user_id, source_url, platform, content, publish_date, thread_id, created_at, notes_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        data,
                    )
                    return {
                        "status": "success",
                        "message": "Final post data saved successfully",
                    }
        except Exception as e:
            raise FailedToSaveFinalPostData(f"Failed to save final post data: {e}") from e