from datetime import UTC, datetime

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def register_payload(**overrides) -> RegisterRequest:
    data = {
        "email": "Test.User@Example.com",
        "password": "ValidPass1!",
        "dateOfBirth": datetime(1990, 1, 1, tzinfo=UTC),
        "firstName": "Ada",
        "lastName": "Lovelace",
        "phoneNumber": "+1 555 123 4567",
    }
    data.update(overrides)
    return RegisterRequest(**data)


class TestValidateUserRegisterPayload:
    def test_accepts_boundary_age_with_timezone_aware_date(self):
        now = datetime.now(UTC)
        thirteen_years_ago_today = datetime(now.year - 13, now.month, now.day, tzinfo=UTC)

        UserService(db=None).validateUserRegisterPayload(
            register_payload(dateOfBirth=thirteen_years_ago_today),
        )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("firstName", "   ", "First name cannot be empty"),
            ("lastName", "", "Last name cannot be empty"),
            ("email", "not-an-email", "Invalid email address"),
            ("password", " ValidPass1!", "Password cannot have leading or trailing whitespace"),
            ("password", "nouppercase1!", "Password must contain at least one uppercase letter"),
            ("password", "NOLOWERCASE1!", "Password must contain at least one lowercase letter"),
            ("password", "NoNumber!!", "Password must contain at least one number"),
            ("password", "NoSpecial12", "Password must contain at least one special character"),
            ("phoneNumber", "1234567", "Invalid phone number length"),
            ("phoneNumber", "1" * 21, "Invalid phone number length"),
        ],
    )
    def test_rejects_invalid_registration_payloads(self, field, value, message):
        payload = register_payload(**{field: value})

        with pytest.raises(RegisterPayloadError) as exc_info:
            UserService(db=None).validateUserRegisterPayload(payload)

        assert exc_info.value.message.startswith(message)

    @pytest.mark.parametrize(
        ("date_of_birth", "message"),
        [
            (datetime(3000, 1, 1, tzinfo=UTC), "Date of birth cannot be in the future"),
            (datetime.now(UTC).replace(year=datetime.now(UTC).year - 12), "You must be at least 13 years old"),
            (datetime(1800, 1, 1, tzinfo=UTC), "Date of birth is not valid"),
        ],
    )
    def test_rejects_invalid_dates_of_birth(self, date_of_birth, message):
        payload = register_payload(dateOfBirth=date_of_birth)

        with pytest.raises(RegisterPayloadError) as exc_info:
            UserService(db=None).validateUserRegisterPayload(payload)

        assert exc_info.value.message.startswith(message)
