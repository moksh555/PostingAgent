import asyncio
from datetime import UTC, datetime

import pytest

from app.errorsHandler.databaseError import (
    FailedToCreateUser,
    FailedToGetUserFromEmail,
    FailedToGetUserFromUserId,
)
from app.errorsHandler.userError import NoEmailError, NoUserIdError
from app.models.userModel import CreateUserModel
from app.repository.userRepository import UserRepository


def db_row(**overrides):
    row = {
        "email": "user@example.com",
        "user_id": "user-123",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "phone_number": "+1 555 123 4567",
        "date_of_birth": datetime(1990, 1, 1, tzinfo=UTC),
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "is_active": True,
        "subscription_type": "free",
        "password_hash": "hashed-password",
    }
    row.update(overrides)
    return row


class FakeDB:
    def __init__(self, *, row=None, fetch_error=None, execute_error=None):
        self.row = row
        self.fetch_error = fetch_error
        self.execute_error = execute_error
        self.fetch_calls = []
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        self.fetch_calls.append((query, args))
        if self.fetch_error:
            raise self.fetch_error
        return self.row

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        if self.execute_error:
            raise self.execute_error
        return "INSERT 0 1"


class TestUserRepository:
    def test_get_user_from_email_maps_public_and_private_models(self):
        db = FakeDB(row=db_row())

        user, private_user = asyncio.run(UserRepository(db).getUserFromEmail("user@example.com"))

        assert user.sub == "user-123"
        assert user.email == "user@example.com"
        assert not hasattr(user, "passwordHash")
        assert private_user.passwordHash == "hashed-password"
        assert db.fetch_calls[0][1] == ("user@example.com",)

    def test_get_user_from_user_id_preserves_not_found_error(self):
        db = FakeDB(row=None)

        with pytest.raises(NoUserIdError):
            asyncio.run(UserRepository(db).getUserFromUserId("missing-user"))

    def test_get_user_from_email_preserves_not_found_error(self):
        db = FakeDB(row=None)

        with pytest.raises(NoEmailError):
            asyncio.run(UserRepository(db).getUserFromEmail("missing@example.com"))

    def test_get_user_from_user_id_wraps_database_failures(self):
        db = FakeDB(fetch_error=RuntimeError("database down"))

        with pytest.raises(FailedToGetUserFromUserId) as exc_info:
            asyncio.run(UserRepository(db).getUserFromUserId("user-123"))

        assert "database down" in exc_info.value.message

    def test_get_user_from_email_wraps_database_failures(self):
        db = FakeDB(fetch_error=RuntimeError("database down"))

        with pytest.raises(FailedToGetUserFromEmail) as exc_info:
            asyncio.run(UserRepository(db).getUserFromEmail("user@example.com"))

        assert "database down" in exc_info.value.message

    def test_create_user_persists_expected_columns_and_returns_public_model(self):
        db = FakeDB()
        create_user = CreateUserModel(
            email="user@example.com",
            sub="user-123",
            userFirstName="Ada",
            userLastName="Lovelace",
            phoneNumber="+1 555 123 4567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            passwordHash="hashed-password",
            subscriptionType="free",
        )

        user = asyncio.run(UserRepository(db).createUser(create_user))

        assert user.sub == "user-123"
        assert not hasattr(user, "passwordHash")
        assert db.execute_calls[0][1] == (
            "user@example.com",
            "user-123",
            "Ada",
            "Lovelace",
            "+1 555 123 4567",
            create_user.dateOfBirth,
            create_user.createdAt,
            True,
            "hashed-password",
            "free",
        )

    def test_create_user_wraps_database_failures(self):
        db = FakeDB(execute_error=RuntimeError("unique violation"))
        create_user = CreateUserModel(
            email="user@example.com",
            sub="user-123",
            userFirstName="Ada",
            userLastName="Lovelace",
            phoneNumber="+1 555 123 4567",
            dateOfBirth=datetime(1990, 1, 1, tzinfo=UTC),
            createdAt=datetime(2026, 1, 1, tzinfo=UTC),
            isActive=True,
            passwordHash="hashed-password",
            subscriptionType="free",
        )

        with pytest.raises(FailedToCreateUser) as exc_info:
            asyncio.run(UserRepository(db).createUser(create_user))

        assert "unique violation" in exc_info.value.message
