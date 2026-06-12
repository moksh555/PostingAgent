import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-at-least-32-bytes",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-at-least-32-bytes",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def user_model():
    from app.models.userModel import UserModel

    return UserModel(
        email="person@example.com",
        sub="user-123",
        userFirstName="person",
        userLastName="example",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2024, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )


@pytest.fixture
def register_payload():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email="New.User@example.com",
        password="StrongPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName="New",
        lastName="User",
        phoneNumber="+15551234567",
    )
