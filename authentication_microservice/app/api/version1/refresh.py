from fastapi import APIRouter, Body, Cookie, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.baseError import AuthenticationError  # type: ignore
from app.errorsHandler.tokenError import CredentialException, TokenError  # type: ignore
from app.models.tokenModel import RefreshRequest, Token  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()

@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
async def refresh(
    auth: AuthenticationService = Depends(get_authentication_service),
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    body: RefreshRequest | None = Body(default=None),
) -> Token:
    try:
        refresh_token = refresh_token_cookie or (body.refresh_token if body else None)
        if not refresh_token:
            raise CredentialException("No Refresh Token provided")
        accessToken = auth.generateAccessTokenFromRefreshToken(refresh_token)
        return accessToken
    except TokenError:
        raise
    except AuthenticationError:
        raise
    except Exception as e:
        raise TokenError(str(e)) from e
