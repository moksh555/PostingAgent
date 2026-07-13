"""Shared test setup for authentication service tests.

The service constructs its settings object at import time, so tests must provide
configuration defaults before importing app modules.
"""

import os
from datetime import UTC, datetime

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-key-with-enough-entropy")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret-key-with-enough-entropy")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def valid_register_payload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email="New.User@Example.COM ",
        password="ValidPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName=" Ada ",
        lastName=" Lovelace ",
        phoneNumber=" +1 555 123 4567 ",
    )
