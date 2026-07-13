import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.userModel import UserModel
from app.services import userService as user_service_module
from app.services.userService import UserService


def _copy_payload(payload, **updates):
    data = payload.model_dump()
    data.update(updates)
    return type(payload)(**data)


@pytest.mark.parametrize(
    ("field_updates", "expected_message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short1!"}, "Password must be at least 10 characters"),
        ({"password": " ValidPass1!"}, "Password cannot have leading or trailing whitespace"),
        ({"password": "validpass1!"}, "Password must contain at least one uppercase letter"),
        ({"password": "VALIDPASS1!"}, "Password must contain at least one lowercase letter"),
        ({"password": "ValidPass!!"}, "Password must contain at least one number"),
        ({"password": "ValidPass11"}, "Password must contain at least one special character"),
        ({"phoneNumber": "123"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime.now(UTC) - timedelta(days=365 * 12)},
            "You must be at least 13 years old to register",
        ),
    ],
)
def test_register_payload_validation_rejects_business_rule_violations(
    valid_register_payload,
    field_updates,
    expected_message,
):
    service = UserService(db=object())
    payload = _copy_payload(valid_register_payload, **field_updates)

    with pytest.raises(RegisterPayloadError, match=expected_message):
        service.validateUserRegisterPayload(payload)


def test_create_user_normalizes_identity_and_hashes_password(
    monkeypatch,
    valid_register_payload,
):
    captured = {}

    class FakeUserRepository:
        def __init__(self, db):
            self.db = db

        async def createUser(self, pending_user):
            captured["pending_user"] = pending_user
            return UserModel(
                email=pending_user.email,
                sub=pending_user.sub,
                userFirstName=pending_user.userFirstName,
                userLastName=pending_user.userLastName,
                phoneNumber=pending_user.phoneNumber,
                dateOfBirth=pending_user.dateOfBirth,
                createdAt=pending_user.createdAt,
                isActive=pending_user.isActive,
                subscriptionType=pending_user.subscriptionType,
            )

    monkeypatch.setattr(user_service_module, "UserRepository", FakeUserRepository)

    service = UserService(db=object())
    user = asyncio.run(service.createUser(valid_register_payload))
    pending_user = captured["pending_user"]

    assert user.email == "new.user@example.com"
    assert pending_user.email == "new.user@example.com"
    assert pending_user.userFirstName == "ada"
    assert pending_user.userLastName == "lovelace"
    assert pending_user.phoneNumber == "+1 555 123 4567"
    assert pending_user.subscriptionType == "free"
    assert pending_user.isActive is True
    assert pending_user.passwordHash != valid_register_payload.password
    assert service._comparePassword(valid_register_payload.password, pending_user.passwordHash)
