import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.userModel import UserModel
from app.services.userService import UserService


def test_validate_user_register_payload_accepts_valid_payload(valid_register_request):
    UserService(db=object()).validateUserRegisterPayload(valid_register_request)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "   ", "First name cannot be empty"),
        ("lastName", "", "Last name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("password", "short1!", "at least 10 characters"),
        ("password", "validpass1!", "uppercase"),
        ("password", "VALIDPASS1!", "lowercase"),
        ("password", "ValidPass!!", "number"),
        ("password", "ValidPass11", "special"),
        ("password", " ValidPass1!", "leading or trailing whitespace"),
        ("phoneNumber", "123", "Invalid phone number length"),
        ("dateOfBirth", datetime.now(UTC) + timedelta(days=1), "future"),
        (
            "dateOfBirth",
            datetime.now(UTC) - timedelta(days=365 * 12),
            "at least 13 years old",
        ),
        ("dateOfBirth", datetime(1800, 1, 1, tzinfo=UTC), "not valid"),
    ],
)
def test_validate_user_register_payload_rejects_invalid_fields(
    valid_register_request,
    field,
    value,
    message,
):
    payload = valid_register_request.model_copy(update={field: value})

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=object()).validateUserRegisterPayload(payload)


def test_create_user_normalizes_profile_fields_and_hashes_password(
    monkeypatch,
    valid_register_request,
):
    import app.services.userService as user_service_module

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

    created_user = asyncio.run(service.createUser(valid_register_request))
    pending_user = captured["pending_user"]

    assert pending_user.email == "person@example.com"
    assert pending_user.userFirstName == "person"
    assert pending_user.userLastName == "example"
    assert pending_user.phoneNumber == "+1 555 123 4567"
    assert pending_user.subscriptionType == "free"
    assert pending_user.isActive is True
    assert pending_user.passwordHash != valid_register_request.password
    assert service._comparePassword(
        valid_register_request.password,
        pending_user.passwordHash,
    )
    assert created_user.email == pending_user.email
    assert created_user.sub == pending_user.sub
