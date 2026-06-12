from datetime import UTC, datetime

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.services import userService as user_service_module


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 12, tzinfo=tz)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(user_service_module, "datetime", FixedDateTime)


def test_validate_register_payload_accepts_policy_compliant_payload(register_payload):
    service = user_service_module.UserService(db=object())

    service.validateUserRegisterPayload(register_payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "   ", "First name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("password", "NoSpecial123", "Password must contain at least one special"),
        ("password", "Short1!", "Password must be at least 10 characters"),
        ("phoneNumber", "1234567", "Invalid phone number length"),
        (
            "dateOfBirth",
            datetime(2020, 1, 1, tzinfo=UTC),
            "You must be at least 13 years old",
        ),
        (
            "dateOfBirth",
            datetime(2027, 1, 1, tzinfo=UTC),
            "Date of birth cannot be in the future",
        ),
    ],
)
def test_validate_register_payload_rejects_high_risk_invalid_fields(
    register_payload,
    field,
    value,
    message,
):
    service = user_service_module.UserService(db=object())
    payload = register_payload.model_copy(update={field: value})

    with pytest.raises(RegisterPayloadError) as exc_info:
        service.validateUserRegisterPayload(payload)

    assert message in exc_info.value.message
