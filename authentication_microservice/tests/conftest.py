import os
from datetime import UTC, datetime

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-long-enough-for-hs256",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-long-enough-for-hs256",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost/test")


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
def private_user_model(user_model):
    from app.models.userModel import UserPrivateModel

    return UserPrivateModel(
        **user_model.model_dump(),
        passwordHash="hashed-password",
    )


@pytest.fixture
def valid_register_request():
    from app.models.registerModel import RegisterRequest

    return RegisterRequest(
        email="Person@Example.COM",
        password="ValidPass1!",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        firstName=" Person ",
        lastName=" Example ",
        phoneNumber=" +1 555 123 4567 ",
    )
