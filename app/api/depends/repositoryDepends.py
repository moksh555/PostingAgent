from app.repository.postgreSQL import PostgreSQLRepository
import functools

@functools.lru_cache(maxsize=1)
def get_postgres_repository_checkpointer() -> PostgreSQLRepository:
    return PostgreSQLRepository()

@functools.lru_cache(maxsize=1)
def get_postgres_repository_posts() -> PostgreSQLRepository:
    return PostgreSQLRepository()