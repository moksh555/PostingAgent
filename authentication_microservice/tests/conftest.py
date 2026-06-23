"""Shared fixtures for authentication microservice tests.

Config is instantiated at app import time, so default environment variables must
be present before tests import application modules.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://example.invalid/test")


@pytest.fixture
def user_row():
    return {
        "email": "user@example.com",
        "user_id": "user-123",
        "first_name": "test",
        "last_name": "user",
        "phone_number": "+15555550123",
        "date_of_birth": datetime(2000, 1, 1, tzinfo=UTC),
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "is_active": True,
        "subscription_type": "free",
        "password_hash": "not-used",
    }


@pytest.fixture
def register_payload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email=" New.User@Example.COM ",
        password="StrongPass1!",
        dateOfBirth=datetime(2000, 1, 1, tzinfo=UTC),
        firstName="  Ada ",
        lastName=" Lovelace ",
        phoneNumber=" +1 (555) 555-0123 ",
    )
