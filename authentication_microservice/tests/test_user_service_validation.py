import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.services.userService import UserService


def test_validate_register_payload_accepts_valid_payload(register_payload_factory):
    service = UserService(db=object())

    service.validateUserRegisterPayload(register_payload_factory())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"firstName": " "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "short"}, "Password must be at least"),
        ({"password": "lowercase1!"}, "uppercase letter"),
        ({"password": "Lowercase!"}, "number"),
        ({"password": "Lowercase1"}, "special character"),
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
def test_validate_register_payload_rejects_risky_inputs(
    register_payload_factory,
    overrides,
    message,
):
    service = UserService(db=object())

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(register_payload_factory(**overrides))


def test_create_user_normalizes_public_fields_and_hashes_password(
    register_payload_factory,
):
    class RecordingDb:
        def __init__(self):
            self.args = None

        async def execute(self, query, *args):
            self.args = args

    db = RecordingDb()
    service = UserService(db=db)
    payload = register_payload_factory(
        email="  USER@Example.COM  ",
        firstName=" Jane ",
        lastName=" DOE ",
        phoneNumber=" 5551234567 ",
    )

    user = asyncio.run(service.createUser(payload))

    assert user.email == "user@example.com"
    assert user.userFirstName == "jane"
    assert user.userLastName == "doe"
    assert user.phoneNumber == "5551234567"
    assert user.subscriptionType == "free"
    assert user.isActive is True

    assert db.args is not None
    inserted_password_hash = db.args[8]
    assert inserted_password_hash != payload.password
    assert service._comparePassword(payload.password, inserted_password_hash)
