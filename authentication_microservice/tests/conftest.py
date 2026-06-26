import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("VERSION", "test")
os.environ.setdefault("AUTHENTICATION_SECRET_KEY", "test-access-secret")
os.environ.setdefault("AUTHENTICATION_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("AUTHENTICATION_ALGORITHM", "HS256")
os.environ.setdefault("AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS", "5")
os.environ.setdefault("POSTGRES_DB_URI", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def client_factory() -> Iterator:
    from app.api.depends.auth import get_authentication_service
    from main import app

    clients: list[TestClient] = []

    def _make_client(auth_service: object) -> TestClient:
        app.dependency_overrides[get_authentication_service] = lambda: auth_service
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make_client

    app.dependency_overrides.clear()
    for client in clients:
        client.close()


@pytest.fixture
def sample_user():
    from app.models.userModel import UserModel

    return UserModel(
        email="user@example.com",
        sub="user-123",
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15551234567",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
        createdAt=datetime(2026, 1, 1, tzinfo=UTC),
        isActive=True,
        subscriptionType="free",
    )
