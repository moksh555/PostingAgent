from datetime import datetime, timedelta, timezone

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def _register_payload(**overrides) -> RegisterRequest:
    data = {
        "email": "person@example.com",
        "password": "ValidPass1!",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=timezone.utc),
        "firstName": "Person",
        "lastName": "Example",
        "phoneNumber": "+15555550123",
    }
    data.update(overrides)
    return RegisterRequest(**data)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"lastName": ""}, "Last name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short1!"}, "Password must be at least 10 characters"),
        ({"password": " validPass1!"}, "Password cannot have leading or trailing"),
        ({"password": "validpass1!"}, "at least one uppercase"),
        ({"password": "VALIDPASS1!"}, "at least one lowercase"),
        ({"password": "ValidPass!!"}, "at least one number"),
        ({"password": "ValidPass12"}, "at least one special"),
        ({"phoneNumber": "1234567"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(timezone.utc) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - 12)},
            "You must be at least 13 years old",
        ),
    ],
)
def test_register_payload_validation_rejects_invalid_business_fields(
    overrides,
    message,
):
    payload = _register_payload(**overrides)

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=object()).validateUserRegisterPayload(payload)


def test_register_payload_validation_accepts_valid_payload():
    UserService(db=object()).validateUserRegisterPayload(_register_payload())
