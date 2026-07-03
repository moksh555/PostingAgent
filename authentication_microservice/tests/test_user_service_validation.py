import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.userModel import UserModel
from app.services import userService as user_service_module
from app.services.userService import UserService


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short"}, "Password must be at least"),
        ({"password": "alllowercase1!"}, "uppercase"),
        ({"password": "ALLUPPERCASE1!"}, "lowercase"),
        ({"password": "NoNumberHere!"}, "number"),
        ({"password": "NoSpecial123"}, "special character"),
        ({"phoneNumber": "123"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime.now(UTC) - timedelta(days=365 * 10)},
            "at least 13 years old",
        ),
    ],
)
def test_validate_register_payload_rejects_business_rule_violations(
    valid_register_payload,
    overrides,
    message,
):
    service = UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(valid_register_payload(**overrides))


def test_validate_register_payload_accepts_valid_payload(valid_register_payload):
    service = UserService(db=object())

    service.validateUserRegisterPayload(valid_register_payload())


def test_create_user_normalizes_profile_and_hashes_password(
    valid_register_payload,
    monkeypatch,
):
    created_rows = []

    class FakeUserRepository:
        def __init__(self, _db):
            pass

        async def createUser(self, pending_user):
            created_rows.append(pending_user)
            return UserModel(
                sub=pending_user.sub,
                email=pending_user.email,
                userFirstName=pending_user.userFirstName,
                userLastName=pending_user.userLastName,
                phoneNumber=pending_user.phoneNumber,
                dateOfBirth=pending_user.dateOfBirth,
                createdAt=pending_user.createdAt,
                isActive=pending_user.isActive,
                subscriptionType=pending_user.subscriptionType,
            )

    monkeypatch.setattr(
        user_service_module,
        "UserRepository",
        FakeUserRepository,
    )
    payload = valid_register_payload()
    service = UserService(db=object())

    user = asyncio.run(service.createUser(payload))

    assert user.email == "user@example.com"
    assert user.userFirstName == "test"
    assert user.userLastName == "user"
    assert user.phoneNumber == "+1 555 123 4567"
    assert user.subscriptionType == "free"
    assert user.isActive is True
    assert len(created_rows) == 1
    pending_user = created_rows[0]
    assert pending_user.passwordHash != payload.password
    assert service._comparePassword(payload.password, pending_user.passwordHash)
