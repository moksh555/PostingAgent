import asyncio
from datetime import UTC, datetime

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


class FakeDb:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


def _years_ago(years: int) -> datetime:
    now = datetime.now(UTC)
    try:
        return now.replace(year=now.year - years)
    except ValueError:
        return now.replace(year=now.year - years, day=28)


def _valid_register_payload(**overrides) -> RegisterRequest:
    data = {
        "email": "User@Example.COM ",
        "password": "StrongPass1!",
        "dateOfBirth": _years_ago(30),
        "firstName": " Test ",
        "lastName": " User ",
        "phoneNumber": " 1234567890 ",
    }
    data.update(overrides)
    return RegisterRequest(**data)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short1!A"}, "Password must be at least 10 characters"),
        ({"password": "StrongPass11"}, "Password must contain at least one special"),
        ({"phoneNumber": "123"}, "Invalid phone number length"),
        ({"dateOfBirth": _years_ago(12)}, "You must be at least 13 years old"),
    ],
)
def test_validate_register_payload_rejects_business_rule_violations(
    overrides,
    message,
):
    service = UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(_valid_register_payload(**overrides))


def test_validate_register_payload_accepts_minimum_age_boundary():
    service = UserService(db=object())

    service.validateUserRegisterPayload(
        _valid_register_payload(dateOfBirth=_years_ago(13))
    )


def test_create_user_normalizes_profile_and_hashes_password():
    db = FakeDb()
    service = UserService(db)
    payload = _valid_register_payload()

    user = asyncio.run(service.createUser(payload))

    assert user.email == "user@example.com"
    assert user.userFirstName == "test"
    assert user.userLastName == "user"
    assert user.phoneNumber == "1234567890"
    assert user.subscriptionType == "free"
    assert user.isActive is True

    assert len(db.executed) == 1
    _query, args = db.executed[0]
    password_hash = args[8]
    assert password_hash != payload.password
    assert service._comparePassword(payload.password, password_hash)
