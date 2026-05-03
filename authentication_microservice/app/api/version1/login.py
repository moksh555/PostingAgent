from fastapi import APIRouter, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.loginError import LoginError  # type: ignore
from app.models.loginModel import LoginRequest, LoginResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
async def login(
    request: LoginRequest,
    auth: AuthenticationService = Depends(get_authentication_service),
) -> LoginResponse:
    try:
        token = await auth.loginUser(request)
        return LoginResponse(
            access_token=token.accessToken,
            refresh_token="",  # TODO: issue refresh token when flow is ready
        )
    except LoginError:
        raise
    except Exception as e:
        raise LoginError(str(e)) from e
