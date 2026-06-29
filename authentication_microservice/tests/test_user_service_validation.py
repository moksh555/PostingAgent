import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def register_payload(**overrides) -> RegisterRequest:
    data = {
        "email": "Person@Example.com",
        "password": "ValidPass1!",
        "dateOfBirth": datetime(2000, 1, 1, tzinfo=UTC),
        "firstName": " Person ",
        "lastName": " Example ",
        "phoneNumber": " +1 555 123 4567 ",
    }
    data.update(overrides)
    return RegisterRequest(**data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "  ", "First name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("password", "Short1!", "Password must be at least 10 characters"),
        ("password", "NoNumber!!!", "Password must contain at least one number"),
        ("phoneNumber", "123", "Invalid phone number length"),
        (
            "dateOfBirth",
            datetime.now(UTC) + timedelta(days=1),
            "Date of birth cannot be in the future",
        ),
    ],
)
def test_register_payload_validation_rejects_business_rule_violations(
    field: str,
    value,
    message: str,
) -> None:
    service = UserService(db=None)  # type: ignore[arg-type]
    payload = register_payload(**{field: value})

    with pytest.raises(RegisterPayloadError, match=message):
        service.validateUserRegisterPayload(payload)


class FakeCreateUserDb:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args) -> None:
        self.execute_calls.append((query, args))


def test_create_user_normalizes_profile_fields_and_hashes_password() -> None:
    db = FakeCreateUserDb()
    service = UserService(db)  # type: ignore[arg-type]
    payload = register_payload()

    user = asyncio.run(service.createUser(payload))

    assert user.email == "person@example.com"
    assert user.userFirstName == "person"
    assert user.userLastName == "example"
    assert user.phoneNumber == "+1 555 123 4567"

    assert len(db.execute_calls) == 1
    _, args = db.execute_calls[0]
    stored_password_hash = args[8]
    assert stored_password_hash != payload.password
    assert service._comparePassword(payload.password, stored_password_hash)
