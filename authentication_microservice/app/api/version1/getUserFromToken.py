from fastapi import APIRouter, Depends, status, Cookie  # type: ignore
from app.api.depends.auth import get_authentication_service
from app.services.authenticationService import AuthenticationService
from app.models.userModel import UserModel
from app.errorsHandler.loginError import NotAuthorized
from app.errorsHandler.baseError import AuthenticationError

router = APIRouter()

@router.get("/getUserFromToken", status_code=status.HTTP_200_OK)
async def getUserFromToken(
    access_token: str | None = Cookie(None),
    refresh_token: str | None = Cookie(None),
    auth: AuthenticationService = Depends(get_authentication_service),
) -> UserModel:
    if not access_token:
        raise NotAuthorized("Unauthorized Access: No Access Token provided")
    if not refresh_token:
        raise NotAuthorized("Unauthorized Access: No Refresh Token provided")
    try:
        return await auth.getUserFromAccessToken(access_token, refresh_token)
    except NotAuthorized:
        raise
    except AuthenticationError:
        raise
    except Exception as e:
        raise NotAuthorized(str(e)) from e