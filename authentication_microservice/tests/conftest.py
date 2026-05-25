import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://user:pass@localhost:5432/test")

from app.api.depends.auth import get_authentication_service  # noqa: E402
from app.models.tokenModel import Token  # noqa: E402
from app.models.userModel import UserModel  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def sample_user() -> UserModel:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=now,
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def fake_auth(sample_user: UserModel) -> Mock:
    auth = Mock()
    auth.generateAccessTokenFromRefreshToken = Mock(
        return_value=Token(accessToken="new-access-token", tokenType="ACCESS_TOKEN"),
    )
    auth.getUserFromAccessToken = AsyncMock(return_value=sample_user)
    auth.loginUser = AsyncMock(
        return_value=(
            Token(accessToken="login-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="login-refresh-token", tokenType="REFRESH_TOKEN"),
        ),
    )
    auth.registerUser = AsyncMock(
        return_value=(
            Token(accessToken="register-access-token", tokenType="ACCESS_TOKEN"),
            Token(accessToken="register-refresh-token", tokenType="REFRESH_TOKEN"),
        ),
    )
    return auth


@pytest.fixture
def client(fake_auth: Mock):
    app.dependency_overrides[get_authentication_service] = lambda: fake_auth
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        test_client.close()
