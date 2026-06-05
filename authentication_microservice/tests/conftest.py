"""Shared authentication test setup."""

import os
from datetime import datetime, timezone

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-key-with-enough-entropy-for-jwt-tests",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-with-enough-entropy-for-jwt-tests",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    now = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=now,
        isActive=True,
        subscriptionType="free",
    )
