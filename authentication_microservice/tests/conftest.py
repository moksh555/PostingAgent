import os
from datetime import UTC, datetime

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def sample_user_row():
    now = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    return {
        "email": "person@example.com",
        "user_id": "user-123",
        "first_name": "person",
        "last_name": "example",
        "phone_number": "+15555550123",
        "date_of_birth": datetime(1990, 5, 1, tzinfo=UTC),
        "created_at": now,
        "is_active": True,
        "subscription_type": "free",
        "password_hash": "unused-in-token-tests",
    }


@pytest.fixture
def sample_user(sample_user_row):
    from app.models.userModel import UserModel

    return UserModel(
        email=sample_user_row["email"],
        sub=str(sample_user_row["user_id"]),
        userFirstName=sample_user_row["first_name"],
        userLastName=sample_user_row["last_name"],
        phoneNumber=sample_user_row["phone_number"],
        dateOfBirth=sample_user_row["date_of_birth"],
        createdAt=sample_user_row["created_at"],
        isActive=sample_user_row["is_active"],
        subscriptionType=sample_user_row["subscription_type"],
    )
