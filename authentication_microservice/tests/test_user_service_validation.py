import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.services.userService import UserService


def test_validate_register_payload_accepts_complete_payload(valid_register_payload):
    UserService(db=object()).validateUserRegisterPayload(valid_register_payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "   ", "First name cannot be empty"),
        ("lastName", "", "Last name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("password", "short", "Password must be at least 10 characters"),
        ("password", "lowercase1!", "Password must contain at least one uppercase"),
        ("password", "UPPERCASE1!", "Password must contain at least one lowercase"),
        ("password", "NoDigits!!", "Password must contain at least one number"),
        ("password", "NoSpecial11", "Password must contain at least one special"),
        ("password", " StrongPass1!", "Password cannot have leading or trailing"),
        ("phoneNumber", "1234567", "Invalid phone number length"),
    ],
)
def test_validate_register_payload_rejects_invalid_fields(
    valid_register_payload,
    field,
    value,
    message,
):
    payload = valid_register_payload.model_copy(update={field: value})

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=object()).validateUserRegisterPayload(payload)


@pytest.mark.parametrize(
    ("date_of_birth", "message"),
    [
        (
            datetime.now(UTC) + timedelta(days=1),
            "Date of birth cannot be in the future",
        ),
        (
            datetime.now(UTC).replace(year=datetime.now(UTC).year - 12),
            "You must be at least 13 years old",
        ),
        (
            datetime.now(UTC).replace(year=datetime.now(UTC).year - 121),
            "Date of birth is not valid",
        ),
    ],
)
def test_validate_register_payload_rejects_invalid_birth_dates(
    valid_register_payload,
    date_of_birth,
    message,
):
    payload = valid_register_payload.model_copy(update={"dateOfBirth": date_of_birth})

    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=object()).validateUserRegisterPayload(payload)


def test_create_user_normalizes_identity_fields_and_hashes_password(valid_register_payload):
    class FakeDb:
        def __init__(self):
            self.execute_calls = []

        async def execute(self, query, *args):
            self.execute_calls.append((query, args))

    fake_db = FakeDb()
    service = UserService(fake_db)

    created = asyncio.run(service.createUser(valid_register_payload))

    assert created.email == "user@example.com"
    assert created.userFirstName == "ada"
    assert created.userLastName == "lovelace"
    assert created.phoneNumber == "+1 555 123 4567"
    assert created.subscriptionType == "free"
    assert created.isActive is True

    assert len(fake_db.execute_calls) == 1
    _query, args = fake_db.execute_calls[0]
    password_hash = args[8]
    assert password_hash != valid_register_payload.password
    assert service._comparePassword(valid_register_payload.password, password_hash)
