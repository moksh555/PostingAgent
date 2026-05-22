from datetime import UTC, datetime, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError


def test_validate_user_register_payload_accepts_valid_payload(
    user_service,
    valid_register_payload,
):
    user_service.validateUserRegisterPayload(valid_register_payload)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"firstName": "   "}, "First name cannot be empty"),
        ({"email": "not-an-email"}, "Invalid email address"),
        ({"password": "Short1!"}, "Password must be at least"),
        ({"password": "validpass1!"}, "uppercase"),
        ({"password": " ValidPass1!"}, "leading or trailing whitespace"),
        ({"password": "ValidPass!!"}, "number"),
        ({"password": "ValidPass12"}, "special character"),
        ({"phoneNumber": "12345"}, "Invalid phone number length"),
        (
            {"dateOfBirth": datetime.now(UTC) + timedelta(days=1)},
            "Date of birth cannot be in the future",
        ),
        (
            {"dateOfBirth": datetime.now(UTC) - timedelta(days=365 * 12)},
            "at least 13 years old",
        ),
    ],
)
def test_validate_user_register_payload_rejects_business_rule_violations(
    user_service,
    valid_register_payload,
    updates,
    message,
):
    invalid_payload = valid_register_payload.model_copy(update=updates)

    with pytest.raises(RegisterPayloadError, match=message):
        user_service.validateUserRegisterPayload(invalid_payload)
