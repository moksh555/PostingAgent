"""Shared fixtures for authentication microservice tests.

The app config is instantiated at import time, so tests must provide settings
before importing modules from ``app`` or ``configurations``.
"""

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost/test")


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="person",
        userLastName="example",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1995, 5, 1, tzinfo=timezone.utc),
        createdAt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )
