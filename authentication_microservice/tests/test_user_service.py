import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.userModel import UserModel
from app.services import userService as user_module
from app.services.userService import UserService


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "Short1!"}, "Password must be at least"),
        ({"password": "StrongPass1! "}, "leading or trailing whitespace"),
        ({"password": "StrongPassword!"}, "at least one number"),
        ({"phoneNumber": "123"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime(1900, 1, 1, tzinfo=UTC)},
            "Date of birth is not valid",
        ),
    ],
)
def test_validate_register_payload_rejects_business_rule_violations(
    registerPayload,
    updates,
    message,
):
    payload = registerPayload.model_copy(update=updates)

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=None).validateUserRegisterPayload(payload)  # type: ignore[arg-type]


def test_create_user_normalizes_fields_hashes_password_and_persists(
    monkeypatch,
    registerPayload,
):
    captured_users = []

    class FakeUserRepository:
        def __init__(self, db):
            self.db = db

        async def createUser(self, user):
            captured_users.append(user)
            return UserModel(
                email=user.email,
                sub=user.sub,
                userFirstName=user.userFirstName,
                userLastName=user.userLastName,
                phoneNumber=user.phoneNumber,
                dateOfBirth=user.dateOfBirth,
                createdAt=user.createdAt,
                isActive=user.isActive,
                subscriptionType=user.subscriptionType,
            )

    monkeypatch.setattr(user_module, "UserRepository", FakeUserRepository)

    user = asyncio.run(async_create_user(registerPayload))

    assert user.email == "person@example.com"
    assert user.userFirstName == "person"
    assert user.userLastName == "example"
    assert user.phoneNumber == "+1 555 123 4567"
    assert user.subscriptionType == "free"
    assert user.isActive is True

    assert len(captured_users) == 1
    persisted = captured_users[0]
    assert persisted.email == "person@example.com"
    assert persisted.passwordHash != registerPayload.password
    assert persisted.passwordHash


async def async_create_user(registerPayload):
    return await UserService(db=None).createUser(registerPayload)  # type: ignore[arg-type]
