import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import TokenModel
from app.models.userModel import UserModel
from app.services import authenticationService as authentication_service_module
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _user_model(sub: str = "user-123", email: str = "user@example.com") -> UserModel:
    return UserModel(
        email=email,
        sub=sub,
        userFirstName="test",
        userLastName="user",
        phoneNumber="+15555550123",
        dateOfBirth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        createdAt=datetime(2024, 1, 1, tzinfo=timezone.utc),
        isActive=True,
        subscriptionType="free",
    )


def test_refresh_token_uses_dedicated_secret_and_rejects_access_token() -> None:
    auth = AuthenticationService(db=object())
    token_data = TokenModel(sub="user-123", email="user@example.com")

    access_token = auth._encodeAccessToken(token_data, timedelta(minutes=5))
    refresh_token = auth._encodeRefreshToken(token_data, timedelta(days=1))

    with pytest.raises(CredentialException):
        auth.generateAccessTokenFromRefreshToken(access_token)

    new_access_token = auth.generateAccessTokenFromRefreshToken(refresh_token)

    assert new_access_token.tokenType == "ACCESS_TOKEN"
    decoded = jwt.decode(
        new_access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "user@example.com"


@pytest.mark.parametrize(
    ("refresh_payload", "expected_error"),
    [
        (
            {
                "sub": "user-123",
                "email": "user@example.com",
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            NotAuthorized,
        ),
        (
            {
                "email": "user@example.com",
                "exp": datetime.now(timezone.utc) + timedelta(days=1),
            },
            CredentialException,
        ),
    ],
)
def test_generate_access_token_rejects_expired_or_subjectless_refresh_tokens(
    refresh_payload: dict[str, object],
    expected_error: type[Exception],
) -> None:
    auth = AuthenticationService(db=object())
    refresh_token = jwt.encode(
        refresh_payload,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithm=config.AUTHENTICATION_ALGORITHM,
    )

    with pytest.raises(expected_error):
        auth.generateAccessTokenFromRefreshToken(refresh_token)


def test_expired_access_token_uses_refresh_token_and_retries_user_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = AuthenticationService(db=object())
    user = _user_model()
    user_ids_seen: list[str] = []
    token_data = TokenModel(sub=user.sub, email=user.email)
    expired_access_token = auth._encodeAccessToken(
        token_data,
        timedelta(seconds=-1),
    )
    refresh_token = auth._encodeRefreshToken(token_data, timedelta(days=1))

    class FakeUserService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def getUserFromUserId(self, user_id: str) -> UserModel:
            user_ids_seen.append(user_id)
            return user

    monkeypatch.setattr(authentication_service_module, "UserService", FakeUserService)

    result = asyncio.run(
        auth.getUserFromAccessToken(expired_access_token, refresh_token),
    )

    assert result == user
    assert user_ids_seen == [user.sub]


def test_invalid_access_token_does_not_attempt_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = AuthenticationService(db=object())

    def fail_if_refreshed(refresh_token: str) -> None:
        raise AssertionError(f"unexpected refresh attempt with {refresh_token}")

    monkeypatch.setattr(auth, "generateAccessTokenFromRefreshToken", fail_if_refreshed)

    with pytest.raises(CredentialException):
        asyncio.run(auth.getUserFromAccessToken("not-a-jwt", "refresh-token"))
