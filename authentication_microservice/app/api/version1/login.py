from fastapi import APIRouter, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.loginError import LoginError  # type: ignore
from app.models.loginModel import LoginRequest, LoginResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore
from fastapi import Response # type: ignore
router = APIRouter()


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
async def login(
    request: LoginRequest,
    response: Response,
    auth: AuthenticationService = Depends(get_authentication_service),
) -> LoginResponse:
    try:
        (accessToken, refreshToken) = await auth.loginUser(request)
        response.set_cookie(
            key="refresh_token",
            value=refreshToken.accessToken,
            httponly=True,
            secure=True,
            max_age= 3600 * 24 * 5 #
        )
        response.set_cookie(
            key="access_token",
            value=accessToken.accessToken,
            httponly=True,
            secure=True,
            max_age= 1800
        )
        return LoginResponse(
            message="Login successful",
            status="success",
        )
    except LoginError:
        raise
    except Exception as e:
        raise LoginError(str(e)) from e
