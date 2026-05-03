from fastapi import APIRouter, status  # type: ignore

from app.errorsHandler.loginError import LoginError  # type: ignore
from app.models.loginModel import LoginRequest, LoginResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()
_auth = AuthenticationService()


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
async def login(request: LoginRequest) -> LoginResponse:
    try:
        token = await _auth.loginUser(request)
        return LoginResponse(
            access_token=token.accessToken,
            refresh_token="",  # TODO: issue refresh token when flow is ready
        )
    except LoginError:
        raise
    except Exception as e:
        raise LoginError(str(e)) from e
