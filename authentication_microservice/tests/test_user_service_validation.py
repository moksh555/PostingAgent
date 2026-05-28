from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def _years_ago(years: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=years * 365)


@pytest.fixture
def valid_register_payload():
    return RegisterRequest(
        email="user@example.com",
        password="ValidPass1!",
        dateOfBirth=_years_ago(20),
        firstName="Test",
        lastName="User",
        phoneNumber="+15555550123",
    )


def test_valid_registration_payload_is_accepted(valid_register_payload):
    UserService(db=object()).validateUserRegisterPayload(valid_register_payload)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "Aa1!"}, "Password must be at least 10 characters"),
        ({"password": " ValidPass1!"}, "Password cannot have leading or trailing whitespace"),
        ({"phoneNumber": "1234"}, "Invalid phone number length"),
        ({"dateOfBirth": datetime.now(UTC) + timedelta(days=1)}, "Date of birth cannot be in the future"),
        ({"dateOfBirth": _years_ago(12)}, "You must be at least 13 years old to register"),
    ],
)
def test_invalid_registration_payloads_are_rejected(
    valid_register_payload,
    updates,
    message,
):
    payload = valid_register_payload.model_copy(update=updates)

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=object()).validateUserRegisterPayload(payload)
