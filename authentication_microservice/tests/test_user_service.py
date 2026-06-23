import asyncio
from datetime import UTC, datetime

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services import userService as user_service_module
from app.services.userService import UserService


class FakeDb:
    def __init__(self):
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "INSERT 0 1"


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 6, 23, tzinfo=UTC)
        return value if tz else value.replace(tzinfo=None)


def payload_with(register_payload, **overrides):
    data = register_payload.model_dump()
    data.update(overrides)
    return RegisterRequest(**data)


@pytest.fixture(autouse=True)
def freeze_user_service_clock(monkeypatch):
    monkeypatch.setattr(user_service_module, "datetime", FrozenDateTime)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"password": "NoSpecial123"}, "Password must contain at least one special"),
        ({"phoneNumber": "555-12"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime(2013, 6, 24, tzinfo=UTC)},
            "You must be at least 13 years old to register",
        ),
        (
            {"dateOfBirth": datetime(2026, 6, 24, tzinfo=UTC)},
            "Date of birth cannot be in the future",
        ),
    ],
)
def test_validate_register_payload_rejects_business_rule_edges(
    register_payload,
    overrides,
    message,
):
    service = UserService(FakeDb())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(payload_with(register_payload, **overrides))


def test_create_user_normalizes_profile_fields_and_hashes_password(register_payload):
    db = FakeDb()
    service = UserService(db)

    user = asyncio.run(service.createUser(register_payload))

    assert user.email == "new.user@example.com"
    assert user.userFirstName == "ada"
    assert user.userLastName == "lovelace"
    assert user.phoneNumber == "+1 (555) 555-0123"
    assert user.subscriptionType == "free"

    assert len(db.execute_calls) == 1
    _query, args = db.execute_calls[0]
    assert args[0] == "new.user@example.com"
    assert args[2] == "ada"
    assert args[3] == "lovelace"
    assert args[4] == "+1 (555) 555-0123"
    assert args[8] != register_payload.password
    assert service._comparePassword(register_payload.password, args[8])
