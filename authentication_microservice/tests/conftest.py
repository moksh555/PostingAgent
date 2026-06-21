"""Shared pytest setup for authentication service tests.

Configuration is instantiated at import time in ``configurations.config``, so
tests must provide deterministic defaults before importing app modules.
"""

import os
from datetime import datetime

import pytest


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://unused:unused@localhost/unused")


@pytest.fixture
def authService():
    from app.services.authenticationService import AuthenticationService

    return AuthenticationService(db=None)


@pytest.fixture
def tokenPayload():
    from app.models.tokenModel import TokenModel

    return TokenModel(sub="user-123", email="user@example.com")


@pytest.fixture
def userModel():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="Test",
        userLastName="User",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1),
        createdAt=datetime(2026, 1, 1),
        isActive=True,
        subscriptionType="free",
    )
