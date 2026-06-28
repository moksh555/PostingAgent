import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.models.userModel import UserModel
from app.services import userService as user_service_module
from app.services.userService import UserService


def _valid_register_request(**overrides) -> RegisterRequest:
    values = {
        "email": "user@example.com",
        "password": "StrongPass1!",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
        "firstName": "Ada",
        "lastName": "Lovelace",
        "phoneNumber": "+1 555 123 4567",
    }
    values.update(overrides)
    return RegisterRequest(**values)


def _years_ago(years: int) -> datetime:
    today = datetime.now(UTC).date()
    return datetime(today.year - years, today.month, today.day, tzinfo=UTC)


@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"lastName": "   "}, "Last name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": ""}, "Password cannot be empty"),
        ({"password": "Short1!"}, "Password must be at least 10 characters"),
        ({"password": "lowercase1!"}, "uppercase letter"),
        ({"password": "UPPERCASE1!"}, "lowercase letter"),
        ({"password": "NoDigits!!"}, "number"),
        ({"password": "NoSpecial1"}, "special character"),
        ({"password": " StrongPass1!"}, "leading or trailing whitespace"),
        ({"phoneNumber": "1234567"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        ({"dateOfBirth": _years_ago(12)}, "at least 13 years old"),
        ({"dateOfBirth": _years_ago(121)}, "Date of birth is not valid"),
    ],
)
def test_validate_register_payload_rejects_business_rule_violations(
    payload_overrides,
    message,
):
    service = UserService(db=object())  # type: ignore[arg-type]

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(_valid_register_request(**payload_overrides))


def test_validate_register_payload_accepts_valid_request():
    service = UserService(db=object())  # type: ignore[arg-type]

    service.validateUserRegisterPayload(_valid_register_request())


def test_create_user_normalizes_identity_fields_and_hashes_password(monkeypatch):
    captured_users = []
    fixed_user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

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

    monkeypatch.setattr(user_service_module.uuid, "uuid4", lambda: fixed_user_id)
    monkeypatch.setattr(user_service_module, "UserRepository", FakeUserRepository)

    service = UserService(db=object())  # type: ignore[arg-type]
    payload = _valid_register_request(
        email="  USER@Example.COM  ",
        firstName="  Ada  ",
        lastName="  Lovelace  ",
        phoneNumber="  +1 555 123 4567  ",
    )

    result = asyncio.run(service.createUser(payload))

    assert len(captured_users) == 1
    created_user = captured_users[0]
    assert created_user.sub == str(fixed_user_id)
    assert created_user.email == "user@example.com"
    assert created_user.userFirstName == "ada"
    assert created_user.userLastName == "lovelace"
    assert created_user.phoneNumber == "+1 555 123 4567"
    assert created_user.subscriptionType == "free"
    assert created_user.isActive is True
    assert created_user.passwordHash != payload.password
    assert service._comparePassword(payload.password, created_user.passwordHash)
    assert result.email == "user@example.com"
    assert result.sub == str(fixed_user_id)
