"""Shared test configuration for the authentication microservice.

The production config object is created at import time, so tests must provide
all required settings before importing application modules.
"""

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-key-with-enough-entropy")
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-with-enough-entropy",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://user:pass@localhost:5432/test")


@pytest.fixture
def auth_service():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(db=object())


@pytest.fixture
def token_model():
    from app.models.tokenModel import TokenModel

    return TokenModel(sub="user-123", email="user@example.com")


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="1234567890",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )
