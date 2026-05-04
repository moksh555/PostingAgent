"""User lifecycle helpers (registration validation; extend with DB / profile logic)."""

import uuid
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email #type: ignore
from pwdlib import PasswordHash #type: ignore

from app.errorsHandler.registerError import RegisterPayloadError
from app.models.registerModel import RegisterRequest
from app.models.userModel import (
    UserModel, 
    CreateUserModel,
    UserPrivateModel
)
from app.errorsHandler.userError import NoEmailError
from app.repository.postgreSql import PostgreSQLRepository
from app.repository.userRepository import UserRepository
from app.errorsHandler.databaseError import (
    FailedToGetUserFromEmail
    )

_password_hasher = PasswordHash.recommended()

_MIN_PASSWORD_LEN = 10
_PASSWORD_SPECIAL = set("!@#$%^&*()_+-=[]{}|;:,.<>?/`~")
_MIN_AGE_YEARS = 13
_MAX_AGE_YEARS = 120
_PHONE_MIN_LEN = 8
_PHONE_MAX_LEN = 20


class UserService:
    def __init__(self, db: PostgreSQLRepository) -> None:
        self.db = db

    def validateUserRegisterPayload(self, payload: RegisterRequest) -> None:
        """
        Apply registration rules beyond Pydantic shape validation.

        Raises ``RegisterPayloadError`` (422 / payload_error) with a short message
        for the first violation. Call from the register route before persisting.
        """
        self._validateNames(payload)
        self._validateEmail(payload.email)
        self._validatePassword(payload.password)
        self._validatePhone(payload.phoneNumber)
        self._validateDateOfBirth(payload.dateOfBirth)

    async def createUser(self, payload: RegisterRequest) -> UserModel:
        """
        Hash the password and persist a new user.
        """
        password_hash = _password_hasher.hash(payload.password)
        userId = str(uuid.uuid4())
        _pending_user_row = CreateUserModel(
            sub=userId,
            email=payload.email.strip().lower(),
            passwordHash=password_hash,
            dateOfBirth=payload.dateOfBirth,
            userFirstName=payload.firstName.strip().lower(),
            userLastName=payload.lastName.strip().lower(),
            phoneNumber=payload.phoneNumber.strip(),
            subscriptionType="free",
            createdAt=datetime.now(UTC),
            isActive=True,
        )
        user = await UserRepository(self.db).createUser(_pending_user_row)
        return user
    
    async def getUserFromUserId(self, userId: str) -> UserModel:
        return await UserRepository(self.db).getUserFromUserId(userId)
    
    async def getUserFromEmail(self, email: str, private: bool = False) -> UserPrivateModel | UserModel:
        try:
            userRepository = UserRepository(self.db)
            userModel, userPrivateModel = await userRepository.getUserFromEmail(email)
            if private:
                return userPrivateModel
            else:
                return userModel
        except NoEmailError:
            raise
        except Exception as e:
            raise FailedToGetUserFromEmail(f"Failed to get user from email: {e}") from e

    def _comparePassword(self, password: str, passwordHash: str) -> bool:
        return _password_hasher.verify(password, passwordHash)

    def _validateNames(self, payload: RegisterRequest) -> None:
        if not payload.firstName or not payload.firstName.strip():
            raise RegisterPayloadError("First name cannot be empty")
        if not payload.lastName or not payload.lastName.strip():
            raise RegisterPayloadError("Last name cannot be empty")

    def _validateEmail(self, email: str) -> None:
        normalized = email.strip().lower() if email else ""
        if not normalized:
            raise RegisterPayloadError("Email cannot be empty")
        try:
            validate_email(normalized, check_deliverability=False)
        except EmailNotValidError as exc:
            raise RegisterPayloadError("Invalid email address") from exc

    def _validatePassword(self, password: str) -> None:
        if not password:
            raise RegisterPayloadError("Password cannot be empty")
        if len(password) < _MIN_PASSWORD_LEN:
            raise RegisterPayloadError(
                f"Password must be at least {_MIN_PASSWORD_LEN} characters",
            )
        if password.strip() != password:
            raise RegisterPayloadError(
                "Password cannot have leading or trailing whitespace",
            )
        if not any(c.isupper() for c in password):
            raise RegisterPayloadError(
                "Password must contain at least one uppercase letter",
            )
        if not any(c.islower() for c in password):
            raise RegisterPayloadError(
                "Password must contain at least one lowercase letter",
            )
        if not any(c.isdigit() for c in password):
            raise RegisterPayloadError(
                "Password must contain at least one number",
            )
        if not any(c in _PASSWORD_SPECIAL for c in password):
            raise RegisterPayloadError(
                "Password must contain at least one special character "
                "(for example: ! @ # $ % ^ & * _ - + =)",
            )

    def _validatePhone(self, phone: str) -> None:
        stripped = phone.strip() if phone else ""
        if not stripped:
            raise RegisterPayloadError("Phone number cannot be empty")
        digits = sum(1 for ch in stripped if ch.isdigit())
        if digits < _PHONE_MIN_LEN or len(stripped) > _PHONE_MAX_LEN:
            raise RegisterPayloadError("Invalid phone number length")

    def _validateDateOfBirth(self, dob: datetime) -> None:
        today = datetime.now(UTC).date()
        d = dob.astimezone(UTC).date() if dob.tzinfo else dob.date()
        if d > today:
            raise RegisterPayloadError("Date of birth cannot be in the future")
        age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        if age < _MIN_AGE_YEARS:
            raise RegisterPayloadError(
                f"You must be at least {_MIN_AGE_YEARS} years old to register",
            )
        if age > _MAX_AGE_YEARS:
            raise RegisterPayloadError("Date of birth is not valid")
