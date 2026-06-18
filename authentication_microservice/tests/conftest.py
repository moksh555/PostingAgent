"""Shared fixtures for authentication microservice tests.

Configuration is instantiated at import time, so environment defaults must be
present before app modules are imported by tests.
"""

import os
from datetime import datetime, timezone

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret-with-32-bytes-min")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret-with-32-bytes")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://user:pass@localhost/test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Ada",
        userLastName="Lovelace",
        phoneNumber="5551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )
