from app.repository.postgreSQL import PostgreSQLRepository
from app.repository.s3connection import S3Connection

_postgres_repository_checkpointer: PostgreSQLRepository | None = None
_postgres_repository_posts: PostgreSQLRepository | None = None
_s3_connection: S3Connection | None = None

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

def get_s3_connection() -> S3Connection:
    global _s3_connection
    if _s3_connection is None:
        _s3_connection = S3Connection()
    return _s3_connection