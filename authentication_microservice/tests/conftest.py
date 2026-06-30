"""Shared pytest setup for authentication service tests.

The service reads configuration at import time, so test-safe environment values
must be present before any app modules are imported.
"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("VERSION", "test")
os.environ.setdefault(
    "AUTHENTICATION_SECRET_KEY",
    "test-access-secret-at-least-thirty-two-bytes",
)
os.environ.setdefault(
    "AUTHENTICATION_REFRESH_SECRET_KEY",
    "test-refresh-secret-at-least-thirty-two-bytes",
)
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost/test")


@pytest.fixture
def auth_service():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(db=object())


@pytest.fixture
def register_payload_factory():
    from app.models.registerModel import RegisterRequest

    defaults = {
        "email": "User@Example.com",
        "password": "StrongPass1!",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
        "firstName": " Jane ",
        "lastName": " Doe ",
        "phoneNumber": " +1 555 123 4567 ",
    }

    def build(**overrides):
        return RegisterRequest(**(defaults | overrides))

    return build


@pytest.fixture
def user_model_factory():
    from app.models.userModel import UserModel

    def build(sub: str = "user-123", email: str = "user@example.com") -> UserModel:
        return UserModel(
            email=email,
            sub=sub,
            userFirstName="jane",
            userLastName="doe",
            phoneNumber="+15551234567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            subscriptionType="free",
        )

    return build
