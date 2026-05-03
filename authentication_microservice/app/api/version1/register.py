from fastapi import APIRouter, status  # type: ignore

from app.errorsHandler.registerError import RegisterError  # type: ignore
from app.models.registerModel import RegisterRequest, RegisterResponse  # type: ignore
from app.services.authenticationService import AuthenticationService  # type: ignore

router = APIRouter()
_auth = AuthenticationService()


@router.post(
    "/register",
    status_code=status.HTTP_200_OK,
)
async def register(request: RegisterRequest) -> RegisterResponse:
    try:
        token = await _auth.registerUser(request)
        return RegisterResponse(
            access_token=token.accessToken,
            refresh_token="",
        )
    except RegisterError:
        raise
    except Exception as e:
        raise RegisterError(str(e)) from e
