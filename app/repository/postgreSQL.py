from datetime import datetime
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
from psycopg_pool import AsyncConnectionPool  # type: ignore

from configurations.config import config

from app.errorsHandler.errors import (
    FailedToSaveFinalPostData,
    FailedToSaveThreadIdForUser,
    FailedToGetThreads
    )


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
    
    async def saveThreadIdForUser(self, userId: str, threadId: str):
        try:
            async with self.conn.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO users_threads (user_id, thread_id) VALUES (%s, %s) ON CONFLICT (user_id, thread_id) DO UPDATE SET thread_id = %s",
                        (userId, threadId, threadId),
                    )
        except Exception as e:
            raise FailedToSaveThreadIdForUser(f"Failed to save thread id for user: {e}") from e
    
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
    
    async def getThreads(self, userId: str):
        try:
            async with self.conn.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT thread_id FROM users_threads WHERE user_id = %s",
                        (userId,),
                    )
                    response = await cur.fetchall()
                    return response
        except Exception as e:
            raise FailedToGetThreads(f"Failed to get threads: {e}") from e


if __name__ == "__main__":
    import asyncio
    async def main():
        postgresDB = await PostgreSQLRepository.create()
        threads = await postgresDB.getThreads("test_user_rashmi")
    asyncio.run(main())