import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from jwt.exceptions import ExpiredSignatureError

from app.errorsHandler.tokenError import CredentialException
from app.models.tokenModel import Token
from app.models.userModel import UserModel
from app.services.authenticationService import AuthenticationService


class TestGetUserFromAccessToken:
    def test_expired_access_token_uses_refresh_and_retries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_user: UserModel,
    ) -> None:
        service = AuthenticationService(db=object())
        refresh_access = Mock(
            return_value=Token(
                accessToken="refreshed-access-token",
                tokenType="ACCESS_TOKEN",
            ),
        )
        decode_refreshed_access = AsyncMock(return_value=sample_user)

        monkeypatch.setattr(
            service,
            "_decode_access_token_payload",
            Mock(side_effect=ExpiredSignatureError),
        )
        monkeypatch.setattr(
            service,
            "generateAccessTokenFromRefreshToken",
            refresh_access,
        )
        monkeypatch.setattr(service, "decodeAccessToken", decode_refreshed_access)

        user = asyncio.run(
            service.getUserFromAccessToken(
                accessToken="expired-access-token",
                refreshToken="refresh-token",
            ),
        )

        assert user == sample_user
        refresh_access.assert_called_once_with("refresh-token")
        decode_refreshed_access.assert_awaited_once_with("refreshed-access-token")

    def test_invalid_access_token_does_not_use_refresh(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service = AuthenticationService(db=object())
        refresh_access = Mock()

        monkeypatch.setattr(
            service,
            "_decode_access_token_payload",
            Mock(side_effect=CredentialException),
        )
        monkeypatch.setattr(
            service,
            "generateAccessTokenFromRefreshToken",
            refresh_access,
        )

        with pytest.raises(CredentialException):
            asyncio.run(
                service.getUserFromAccessToken(
                    accessToken="invalid-access-token",
                    refreshToken="refresh-token",
                ),
            )

        refresh_access.assert_not_called()
