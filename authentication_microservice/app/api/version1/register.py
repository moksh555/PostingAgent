from fastapi import APIRouter, Depends, status  # type: ignore

from app.api.depends.auth import get_authentication_service
from app.errorsHandler.registerError import RegisterError  # type: ignore
from app.models.registerModel import RegisterRequest, RegisterResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()


@router.post(
    "/register",
    status_code=status.HTTP_200_OK,
)
async def register(
    request: RegisterRequest,
    auth: AuthenticationService = Depends(get_authentication_service),
) -> RegisterResponse:
    try:
        (accessToken, refreshToken) = await auth.registerUser(request)
        return RegisterResponse(
            access_token=accessToken.accessToken,
            refresh_token=refreshToken.accessToken,
        )
    except RegisterError:
        raise
    except Exception as e:
        raise RegisterError(str(e)) from e
