"""Shared fixtures for authentication tests.

The auth service builds its settings object at import time, so test
environment defaults must be present before importing application modules.
"""

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-key-with-enough-entropy",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-with-enough-entropy",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://example.invalid/auth_test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="test",
        userLastName="user",
        phoneNumber="1234567890",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )
