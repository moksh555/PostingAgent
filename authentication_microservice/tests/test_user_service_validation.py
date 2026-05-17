from datetime import UTC, datetime, time, timedelta

import pytest

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.services.userService import UserService


def _date_years_ago(years: int, *, days_offset: int = 0) -> datetime:
    today = datetime.now(UTC).date()
    try:
        birth_date = today.replace(year=today.year - years)
    except ValueError:
        birth_date = today.replace(month=2, day=28, year=today.year - years)
    birth_date += timedelta(days=days_offset)
    return datetime.combine(birth_date, time.min, tzinfo=UTC)


def _register_payload(**overrides: object) -> RegisterRequest:
    data = {
        "email": "valid@example.com",
        "password": "ValidPass1!",
        "dateOfBirth": _date_years_ago(25),
        "firstName": "Ada",
        "lastName": "Lovelace",
        "phoneNumber": "+1 555 123 4567",
    }
    data.update(overrides)
    return RegisterRequest(**data)


def test_register_payload_accepts_exact_minimum_age() -> None:
    UserService(db=None).validateUserRegisterPayload(
        _register_payload(dateOfBirth=_date_years_ago(13))
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firstName", "  ", "First name cannot be empty"),
        ("lastName", "", "Last name cannot be empty"),
        ("email", "not-an-email", "Invalid email address"),
        ("phoneNumber", "1234567", "Invalid phone number length"),
        ("phoneNumber", "1" * 21, "Invalid phone number length"),
    ],
)
def test_register_payload_rejects_identity_and_contact_edge_cases(
    field: str, value: str, message: str
) -> None:
    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=None).validateUserRegisterPayload(
            _register_payload(**{field: value})
        )


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("Short1!", "Password must be at least 10 characters"),
        (" ValidPass1!", "Password cannot have leading or trailing whitespace"),
        ("validpass1!", "Password must contain at least one uppercase letter"),
        ("VALIDPASS1!", "Password must contain at least one lowercase letter"),
        ("ValidPass!!", "Password must contain at least one number"),
        ("ValidPass12", "Password must contain at least one special character"),
    ],
)
def test_register_payload_rejects_weak_passwords(
    password: str, message: str
) -> None:
    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=None).validateUserRegisterPayload(
            _register_payload(password=password)
        )


@pytest.mark.parametrize(
    ("date_of_birth", "message"),
    [
        (_date_years_ago(13, days_offset=1), "You must be at least 13 years old"),
        (datetime.now(UTC) + timedelta(days=1), "Date of birth cannot be in the future"),
        (_date_years_ago(121), "Date of birth is not valid"),
    ],
)
def test_register_payload_rejects_date_of_birth_policy_violations(
    date_of_birth: datetime, message: str
) -> None:
    with pytest.raises(RegisterPayloadError, match=message):
        UserService(db=None).validateUserRegisterPayload(
            _register_payload(dateOfBirth=date_of_birth)
        )
