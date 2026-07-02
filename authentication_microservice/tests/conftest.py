"""Shared fixtures for authentication microservice tests.

The service constructs its config object at import time, so test defaults must
exist before importing any app modules.
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
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost/test")


@pytest.fixture
def valid_register_payload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email=" User@Example.COM ",
        password="StrongPass1!",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        firstName=" Ada ",
        lastName=" Lovelace ",
        phoneNumber=" +1 555 123 4567 ",
    )


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="ada",
        userLastName="lovelace",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )
