import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-32chars-minimum")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret-32chars-minimum")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://unused")


@pytest.fixture
def auth_service():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(db=object())


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-1",
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def auth_route_service(user_model):
    class FakeAuthenticationService:
        def __init__(self):
            self.loginUser = AsyncMock()
            self.registerUser = AsyncMock()
            self.getUserFromAccessToken = AsyncMock(return_value=user_model)

        def generateAccessTokenFromRefreshToken(self, refresh_token: str):
            raise AssertionError(f"Unexpected refresh token: {refresh_token}")

    return FakeAuthenticationService()


@pytest.fixture
def client(auth_route_service):
    from app.api.depends.auth import get_authentication_service
    from main import app

    app.dependency_overrides[get_authentication_service] = lambda: auth_route_service
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        test_client.close()
