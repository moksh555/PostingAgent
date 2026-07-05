import asyncio
from datetime import timedelta

import jwt
import pytest

from app.errorsHandler.tokenError import CredentialException
from app.errorsHandler.loginError import NoEmailorPasswordFound, NotAuthorized
from app.errorsHandler.userError import NoEmailError
from app.models.loginModel import LoginRequest
from app.models.tokenModel import Token, TokenModel
from app.services.authenticationService import AuthenticationService
from configurations.config import config


def _service() -> AuthenticationService:
    return AuthenticationService(db=object())


def test_login_user_normalizes_email_before_authenticating(monkeypatch):
    service = _service()
    observed = {}

    async def authenticate_user(email, password):
        observed["email"] = email
        observed["password"] = password
        return (
            Token(accessToken="access", tokenType="ACCESS_TOKEN"),
            Token(accessToken="refresh", tokenType="REFRESH_TOKEN"),
        )

    monkeypatch.setattr(service, "authenticateUser", authenticate_user)

    access_token, refresh_token = asyncio.run(
        service.loginUser(
            LoginRequest(email=" Person@Example.COM ", password="CorrectPass1!"),
        ),
    )

    assert observed == {
        "email": "person@example.com",
        "password": "CorrectPass1!",
    }
    assert access_token.tokenType == "ACCESS_TOKEN"
    assert refresh_token.tokenType == "REFRESH_TOKEN"


def test_authenticate_user_returns_access_and_refresh_tokens(monkeypatch, private_user_model):
    import app.services.authenticationService as auth_module

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email, private=False):
            assert email == private_user_model.email
            assert private is True
            return private_user_model

        def _comparePassword(self, password, password_hash):
            return password == "CorrectPass1!" and password_hash == "hashed-password"

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    access_token, refresh_token = asyncio.run(
        _service().authenticateUser(private_user_model.email, "CorrectPass1!"),
    )

    assert access_token.tokenType == "ACCESS_TOKEN"
    assert refresh_token.tokenType == "REFRESH_TOKEN"
    access_payload = jwt.decode(
        access_token.accessToken,
        config.AUTHENTICATION_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    refresh_payload = jwt.decode(
        refresh_token.accessToken,
        config.AUTHENTICATION_REFRESH_SECRET_KEY,
        algorithms=[config.AUTHENTICATION_ALGORITHM],
    )
    assert access_payload["sub"] == private_user_model.sub
    assert refresh_payload["sub"] == private_user_model.sub


def test_authenticate_user_maps_unknown_email_to_not_authorized(monkeypatch):
    import app.services.authenticationService as auth_module

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email, private=False):
            raise NoEmailError("not found")

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    with pytest.raises(NotAuthorized, match="Invalid email or password"):
        asyncio.run(_service().authenticateUser("missing@example.com", "CorrectPass1!"))


def test_authenticate_user_rejects_bad_password(monkeypatch, private_user_model):
    import app.services.authenticationService as auth_module

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def getUserFromEmail(self, email, private=False):
            return private_user_model

        def _comparePassword(self, password, password_hash):
            return False

    monkeypatch.setattr(auth_module, "UserService", FakeUserService)

    with pytest.raises(NotAuthorized, match="Invalid password"):
        asyncio.run(_service().authenticateUser(private_user_model.email, "WrongPass1!"))


@pytest.mark.parametrize(
    ("email", "password", "message"),
    [
        ("", "CorrectPass1!", "valid email"),
        ("person@example.com", "", "valid password"),
    ],
)
def test_authenticate_user_rejects_blank_credentials(email, password, message):
    with pytest.raises(NoEmailorPasswordFound, match=message):
        asyncio.run(_service().authenticateUser(email, password))


def test_decode_access_token_rejects_expired_token():
    service = _service()
    expired_token = service._encodeAccessToken(
        TokenModel(sub="user-123", email="person@example.com"),
        timedelta(seconds=-1),
    )

    with pytest.raises(CredentialException, match="Access token expired"):
        asyncio.run(service.decodeAccessToken(expired_token))
