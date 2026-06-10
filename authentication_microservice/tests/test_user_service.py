from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def build_register_request(**overrides) -> RegisterRequest:
    values = {
        "email": "new@example.com",
        "password": "Password!123",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
        "firstName": "New",
        "lastName": "User",
        "phoneNumber": "+15555550123",
    }
    values.update(overrides)
    return RegisterRequest(**values)


def test_validate_register_payload_accepts_valid_user_details():
    service = UserService(db=object())

    service.validateUserRegisterPayload(build_register_request())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": "  "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short"}, "Password must be at least"),
        ({"password": " Password!123 "}, "leading or trailing whitespace"),
        ({"password": "password!123"}, "uppercase"),
        ({"password": "PASSWORD!123"}, "lowercase"),
        ({"password": "Password!!!"}, "number"),
        ({"password": "Password123"}, "special"),
        ({"phoneNumber": "123"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime.now(UTC) - timedelta(days=365 * 10)},
            "You must be at least 13 years old",
        ),
    ],
)
def test_validate_register_payload_rejects_invalid_user_details(overrides, message):
    service = UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(build_register_request(**overrides))
