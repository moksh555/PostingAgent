import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def _register_payload(**overrides) -> RegisterRequest:
    data = {
        "email": "user@example.com",
        "password": "ValidPass1!",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
        "firstName": "Test",
        "lastName": "User",
        "phoneNumber": "+15551234567",
    }
    data.update(overrides)
    return RegisterRequest(**data)


def test_validate_register_payload_accepts_valid_request():
    UserService(db=object()).validateUserRegisterPayload(_register_payload())


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"lastName": ""}, "Last name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": ""}, "Password cannot be empty"),
        ({"password": "Short1!"}, "at least 10 characters"),
        ({"password": " ValidPass1!"}, "leading or trailing whitespace"),
        ({"password": "validpass1!"}, "uppercase letter"),
        ({"password": "VALIDPASS1!"}, "lowercase letter"),
        ({"password": "ValidPassword!"}, "one number"),
        ({"password": "ValidPass123"}, "special character"),
        ({"phoneNumber": "1234567"}, "Invalid phone number length"),
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
def test_validate_register_payload_rejects_business_rule_violations(updates, message):
    service = UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(_register_payload(**updates))


def test_create_user_normalizes_fields_and_hashes_password():
    class FakeDb:
        def __init__(self) -> None:
            self.execute_args = None

        async def execute(self, *args):
            self.execute_args = args
            return "INSERT 0 1"

    fake_db = FakeDb()
    payload = _register_payload(
        email="  MixedCase@Example.COM  ",
        firstName="  Alice ",
        lastName=" Smith  ",
        phoneNumber="  +15557654321  ",
    )

    user = asyncio.run(UserService(fake_db).createUser(payload))

    assert user.email == "mixedcase@example.com"
    assert user.userFirstName == "alice"
    assert user.userLastName == "smith"
    assert user.phoneNumber == "+15557654321"
    assert fake_db.execute_args is not None
    inserted_password_hash = fake_db.execute_args[9]
    assert inserted_password_hash != payload.password
    assert inserted_password_hash
