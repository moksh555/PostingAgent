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


USER_ID = "2db67c55-4a5b-4f4d-86bb-cd4d54f79d83"
CREATED_AT = datetime(2026, 7, 1, 12, tzinfo=UTC)
DATE_OF_BIRTH = datetime(1990, 5, 20, tzinfo=UTC)


def _user_row() -> dict:
    return {
        "email": "user@example.com",
        "user_id": USER_ID,
        "first_name": "test",
        "last_name": "user",
        "phone_number": "+15555550123",
        "date_of_birth": DATE_OF_BIRTH,
        "created_at": CREATED_AT,
        "is_active": True,
        "password_hash": "argon2-password-hash",
        "subscription_type": "free",
    }


class FakeDatabase:
    def __init__(self, row: dict | None = None, error: Exception | None = None):
        self.row = row
        self.error = error
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        if self.error:
            raise self.error
        return self.row

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))
        if self.error:
            raise self.error
        return "INSERT 0 1"


def test_get_user_by_id_maps_database_row_to_public_model():
    db = FakeDatabase(row=_user_row())

    user = asyncio.run(UserRepository(db).getUserFromUserId(USER_ID))

    assert db.fetchrow_calls == [
        ("SELECT * FROM users WHERE user_id = $1", (USER_ID,))
    ]
    assert user.model_dump() == {
        "email": "user@example.com",
        "sub": USER_ID,
        "userFirstName": "test",
        "userLastName": "user",
        "phoneNumber": "+15555550123",
        "dateOfBirth": DATE_OF_BIRTH,
        "createdAt": CREATED_AT,
        "isActive": True,
        "subscriptionType": "free",
    }
    assert "passwordHash" not in user.model_dump()


def test_get_user_by_id_preserves_not_found_error():
    with pytest.raises(NoUserIdError, match="User not found in the database"):
        asyncio.run(UserRepository(FakeDatabase()).getUserFromUserId(USER_ID))


def test_get_user_by_email_returns_separate_public_and_private_models():
    db = FakeDatabase(row=_user_row())

    public_user, private_user = asyncio.run(
        UserRepository(db).getUserFromEmail("user@example.com")
    )

    assert db.fetchrow_calls == [
        ("SELECT * FROM users WHERE email = $1", ("user@example.com",))
    ]
    assert "passwordHash" not in public_user.model_dump()
    assert private_user.passwordHash == "argon2-password-hash"
    assert public_user.sub == private_user.sub == USER_ID
    assert public_user.subscriptionType == private_user.subscriptionType == "free"


def test_get_user_by_email_preserves_not_found_error():
    with pytest.raises(NoEmailError, match="User not found in the database"):
        asyncio.run(
            UserRepository(FakeDatabase()).getUserFromEmail("missing@example.com")
        )


def test_create_user_persists_every_field_and_returns_public_model():
    db = FakeDatabase()
    pending_user = CreateUserModel(
        email="user@example.com",
        sub=USER_ID,
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15555550123",
        dateOfBirth=DATE_OF_BIRTH,
        createdAt=CREATED_AT,
        isActive=True,
        passwordHash="argon2-password-hash",
        subscriptionType="free",
    )

    user = asyncio.run(UserRepository(db).createUser(pending_user))

    query, args = db.execute_calls[0]
    assert "password_hash, subscription_type" in query
    assert args == (
        "user@example.com",
        USER_ID,
        "test",
        "user",
        "+15555550123",
        DATE_OF_BIRTH,
        CREATED_AT,
        True,
        "argon2-password-hash",
        "free",
    )
    assert user.subscriptionType == "free"
    assert "passwordHash" not in user.model_dump()


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    [
        ("get_by_id", FailedToGetUserFromUserId),
        ("get_by_email", FailedToGetUserFromEmail),
        ("create", FailedToCreateUser),
    ],
)
def test_database_failures_are_translated_to_repository_errors(
    operation: str,
    expected_error: type[Exception],
):
    repository = UserRepository(FakeDatabase(error=RuntimeError("database offline")))
    pending_user = CreateUserModel(
        email="user@example.com",
        sub=USER_ID,
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15555550123",
        dateOfBirth=DATE_OF_BIRTH,
        createdAt=CREATED_AT,
        isActive=True,
        passwordHash="argon2-password-hash",
        subscriptionType="free",
    )

    if operation == "get_by_id":
        coroutine = repository.getUserFromUserId(USER_ID)
    elif operation == "get_by_email":
        coroutine = repository.getUserFromEmail("user@example.com")
    else:
        coroutine = repository.createUser(pending_user)

    with pytest.raises(expected_error, match="database offline") as exc_info:
        asyncio.run(coroutine)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
