from fastapi import APIRouter, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.tokenError import TokenError  # type: ignore
from app.models.tokenModel import Token  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()

@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
async def refresh(
    refreshToken: str,
    auth: AuthenticationService = Depends(get_authentication_service),
) -> Token:
    try:
        accessToken = await auth.generateAccessTokenFromRefreshToken(refreshToken)
        return accessToken
    except TokenError:
        raise
    except Exception as e:
        raise TokenError(str(e)) from e
