"""Shared fixtures for authentication service tests.

Configuration is instantiated at import time, so defaults must be present before
any app modules are imported by tests.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-key-that-is-long-enough-for-jwt-signing",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-that-is-long-enough-for-jwt-signing",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("VERSION", "test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )
