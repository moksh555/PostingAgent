"""Shared test fixtures for the authentication service.

Environment defaults must be set before importing application modules because
``configurations.config.config`` is instantiated at import time.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://unused:test@localhost/test")


@pytest.fixture
def tokenData():
    from app.models.tokenModel import TokenModel

    return TokenModel(sub="user-123", email="person@example.com")


@pytest.fixture
def sampleUser():
    from app.models.userModel import UserModel

    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="person",
        userLastName="example",
        phoneNumber="+1 555 123 4567",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def registerPayload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email="Person@Example.COM",
        password="StrongPass1!",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        firstName=" Person ",
        lastName=" Example ",
        phoneNumber=" +1 555 123 4567 ",
    )
