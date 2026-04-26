from app.repository.postgreSQL import PostgreSQLRepository

_postgres_repository_checkpointer: PostgreSQLRepository | None = None
_postgres_repository_posts: PostgreSQLRepository | None = None

async def get_postgres_repository_checkpointer() -> PostgreSQLRepository:
    global _postgres_repository_checkpointer
    if _postgres_repository_checkpointer is None:
        _postgres_repository_checkpointer = await PostgreSQLRepository.create()
    return _postgres_repository_checkpointer

async def get_postgres_repository_posts() -> PostgreSQLRepository:
    global _postgres_repository_posts
    if _postgres_repository_posts is None:
        _postgres_repository_posts = await PostgreSQLRepository.create()
    return _postgres_repository_posts