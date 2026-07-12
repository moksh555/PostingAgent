"""Shared test configuration for authentication microservice tests.

The application instantiates `config` at import time, so tests must provide
settings before importing app modules.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-key-that-is-long-enough-for-hs256",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-key-that-is-long-enough-for-hs256",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="Person",
        userLastName="Example",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )
