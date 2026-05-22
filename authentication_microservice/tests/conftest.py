"""Shared authentication service test fixtures.

The service creates its configuration object at import time, so these defaults
must be present before any app modules are imported by tests.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-key")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret-key")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://unused")


class FakeDB:
    """Placeholder DB object for tests that mock at the service boundary."""


@pytest.fixture
def auth_service():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(FakeDB())


@pytest.fixture
def user_service():
    from app.services.userService import UserService

    return UserService(FakeDB())


@pytest.fixture
def token_data():
    from app.models.tokenModel import TokenModel

    return TokenModel(sub="user-123", email="user@example.com")


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="jane",
        userLastName="doe",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 5, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def valid_register_payload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email="User@example.com",
        password="ValidPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName="Jane",
        lastName="Doe",
        phoneNumber="+15551234567",
    )
