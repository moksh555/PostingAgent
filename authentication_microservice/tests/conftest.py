import os
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://example.invalid/posting_agent_test")


@pytest.fixture
def auth_service():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(db=object())


@pytest.fixture
def user_model_factory():
    from app.models.userModel import UserModel

    def build_user(sub: str = "user-123", email: str = "user@example.com") -> UserModel:
        return UserModel(
            sub=sub,
            email=email,
            userFirstName="test",
            userLastName="user",
            phoneNumber="+15551234567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )

    return build_user


@pytest.fixture
def valid_register_payload():
    from app.models.registerModel import RegisterRequest

    def build_payload(**overrides) -> RegisterRequest:
        payload = {
            "email": " User@Example.COM ",
            "password": "StrongPass1!",
            "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
            "firstName": " Test ",
            "lastName": " User ",
            "phoneNumber": " +1 555 123 4567 ",
        }
        payload.update(overrides)
        return RegisterRequest(**payload)

    return build_payload


@pytest.fixture
def client_factory():
    from app.api.depends.auth import get_authentication_service
    from app.api.router import router
    from app.errorsHandler.baseError import AuthenticationError

    clients: list[TestClient] = []

    def build_client(auth_service_override) -> TestClient:
        app = FastAPI()

        @app.exception_handler(AuthenticationError)
        async def auth_error_handler(
            _request: Request,
            exc: AuthenticationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message},
            )

        app.include_router(router)
        app.dependency_overrides[get_authentication_service] = (
            lambda: auth_service_override
        )
        client = TestClient(app)
        clients.append(client)
        return client

    yield build_client

    for client in clients:
        client.close()
