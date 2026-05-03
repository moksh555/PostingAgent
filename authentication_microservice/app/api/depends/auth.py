from fastapi import Request  # type: ignore

from app.repository.postgreSql import PostgreSQLRepository
from app.services.authenticationService import AuthenticationService


def get_postgres(request: Request) -> PostgreSQLRepository:
    return request.app.state.db


def get_authentication_service(
    request: Request,
) -> AuthenticationService:
    return AuthenticationService(request.app.state.db)
