import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.userModel import UserModel
from app.services import userService as user_service_module


class FakeUserRepository:
    def __init__(self):
        self.created_user = None

    async def createUser(self, user):
        self.created_user = user
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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "  ", "First name cannot be empty"),
        ("lastName", "", "Last name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("password", "short1!", "Password must be at least 10 characters"),
        ("password", " StrongPass1! ", "Password cannot have leading"),
        ("password", "StrongPass11", "Password must contain at least one special"),
        ("phoneNumber", "123", "Invalid phone number length"),
        ("dateOfBirth", datetime.now(UTC) + timedelta(days=1), "future"),
        ("dateOfBirth", datetime.now(UTC) - timedelta(days=365 * 12), "at least 13"),
        ("dateOfBirth", datetime.now(UTC) - timedelta(days=365 * 121), "not valid"),
    ],
)
def test_validate_register_payload_rejects_business_rule_violations(
    valid_register_payload,
    field,
    value,
    message,
):
    payload = valid_register_payload.model_copy(update={field: value})
    service = user_service_module.UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(payload)


def test_create_user_normalizes_fields_and_hashes_password(
    valid_register_payload,
    monkeypatch,
):
    fake_repo = FakeUserRepository()
    monkeypatch.setattr(
        user_service_module,
        "UserRepository",
        lambda db: fake_repo,
    )
    service = user_service_module.UserService(db=object())

    created = asyncio.run(service.createUser(valid_register_payload))

    pending = fake_repo.created_user
    assert pending is not None
    assert pending.email == "user@example.com"
    assert pending.userFirstName == "test"
    assert pending.userLastName == "user"
    assert pending.phoneNumber == "+1 555 123 4567"
    assert pending.subscriptionType == "free"
    assert pending.isActive is True
    assert pending.passwordHash != valid_register_payload.password
    assert service._comparePassword(valid_register_payload.password, pending.passwordHash)
    assert created.email == "user@example.com"
    assert created.sub == pending.sub
