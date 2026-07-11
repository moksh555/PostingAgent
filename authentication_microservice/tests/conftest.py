import os
from datetime import datetime, timezone

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "access-secret-for-tests-access-secret-for-tests-access-secret-for-tests",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "refresh-secret-for-tests-refresh-secret-for-tests-refresh-secret-for-tests",
)


from app.models.userModel import UserModel  # noqa: E402
from app.services.authenticationService import AuthenticationService  # noqa: E402


@pytest.fixture
def auth_service() -> AuthenticationService:
    return AuthenticationService(db=object())


@pytest.fixture
def sample_user() -> UserModel:
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=stamp,
        isActive=True,
        subscriptionType="free",
    )
