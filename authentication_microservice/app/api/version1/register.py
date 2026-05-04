from fastapi import APIRouter, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.registerError import RegisterError  # type: ignore
from app.models.registerModel import RegisterRequest, RegisterResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore
from fastapi import Response # type: ignore
router = APIRouter()


@router.post(
    "/register",
    status_code=status.HTTP_200_OK,
)
async def register(
    request: RegisterRequest,
    response: Response,
    auth: AuthenticationService = Depends(get_authentication_service),
) -> RegisterResponse:
    try:
        (accessToken, refreshToken) = await auth.registerUser(request)
        response.set_cookie(
            key="refresh_token",
            value=refreshToken.accessToken,
            httponly=True,
            secure=True,
            max_age= 3600 * 24 * 5
        )
        response.set_cookie(
            key="access_token",
            value=accessToken.accessToken,
            httponly=True,
            secure=True,
            max_age= 1800
        )
        return RegisterResponse(
            message="Register successful",
            status="success",
        )
    except RegisterError:
        raise
    except Exception as e:
        raise RegisterError(str(e)) from e
