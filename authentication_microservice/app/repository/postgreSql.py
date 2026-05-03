import asyncpg #type: ignore
from typing import Any
from app.errorsHandler.databaseError import (
    FailedToFetch, 
    FailedToFetchRow, 
    FailedToFetchValue, 
    FailedToExecuteStatement,
)

class PostgreSQLRepository:
    
    def __init__(
        self,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
        max_inactive_connection_lifetime: float = 300.0,
        command_timeout: float = 60.0,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._max_inactive_connection_lifetime = max_inactive_connection_lifetime
        self._command_timeout = command_timeout
        self._pool: asyncpg.Pool | None = None
    
    async def connect(self) -> None:
        """Create the connection pool. Call once at app startup."""
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            max_inactive_connection_lifetime=self._max_inactive_connection_lifetime,
            command_timeout=self._command_timeout,
        )
    
    async def disconnect(self) -> None:
        """Drain and close the pool. Call once at app shutdown."""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    @property
    def pool(self) -> asyncpg.pool.Pool:
        if self._pool is None:
            raise RuntimeError("PostgreSQL pool not initialized")
        return self._pool
    
    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Return all rows."""
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            raise FailedToFetch(f"Failed to fetch: {e}") from e

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Return a single row, or None."""
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            raise FailedToFetchRow(f"Failed to fetch row: {e}") from e

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """Return a single scalar value."""
        try:        
            async with self.pool.acquire() as conn:
                    return await conn.fetchval(query, *args, column=column)
        except Exception as e:  
            raise FailedToFetchValue(f"Failed to fetch value: {e}") from e

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a statement (INSERT/UPDATE/DELETE). Returns status string."""
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            raise FailedToExecuteStatement(f"Failed to execute statement: {e}") from e

    async def executemany(self, query: str, args: list[tuple]) -> None:
        """Bulk-execute a statement with multiple argument sets."""
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(query, args)
        except Exception as e:
            raise FailedToExecuteStatement(f"Failed to execute many statements: {e}") from e
    
    


