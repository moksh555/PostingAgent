from app.models.registerModel import RegisterRequest
from app.models.loginModel import (
    LoginRequest,
)
from app.errorsHandler.loginError import (
    LoginError, 
    NoEmailorPasswordFound,
    NotAuthorized,
)
from app.errorsHandler.tokenError import (
    CredentialException
)
from app.models.tokenModel import (
    TokenModel,
    Token
)
from app.errorsHandler.registerError import (
    RegisterPayloadError,
    RegisterError,
)
from app.services.userService import UserService
from app.repository.postgreSql import PostgreSQLRepository
from app.errorsHandler.userError import NoEmailError
from fastapi import Depends #type: ignore
from configurations.config import config
from fastapi.security import OAuth2PasswordBearer #type: ignore
from datetime import datetime, timedelta, timezone
from typing import Annotated
import jwt #type:ignore
from jwt.exceptions import InvalidTokenError #type:ignore

from app.models.userModel import UserModel

class AuthenticationService:
    OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")

    def __init__(self, db: PostgreSQLRepository) -> None:
        self._db = db

    async def loginUser(self, userPayload: LoginRequest) -> Token:

        try:
            email = userPayload.email.strip().lower()
            password = userPayload.password

            token = await self.authenticateUser(email, password)
            return token
        except LoginError:
            raise
        except Exception as e:
            raise LoginError(str(e)) from e
    
    async def registerUser(self, userPayload: RegisterRequest) -> Token:
        user_service = UserService(self._db)
        try:
            user_service.validateUserRegisterPayload(userPayload)
        except RegisterPayloadError:
            raise
        except Exception as e:
            raise RegisterError(str(e)) from e

        try:
            userId = await user_service.createUser(userPayload)
        except RegisterError:
            raise
        except Exception as e:
            raise RegisterError(str(e)) from e

        try:
            access_token_expires = timedelta(
                minutes=config.AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES,
            )
            data = TokenModel(sub=userId.sub, email=userId.email)
            access_token = self.encodeAccessToken(data, access_token_expires)
            return Token(
                accessToken=access_token,
                tokenType="bearer",
            )
        except Exception as e:
            raise RegisterError(str(e)) from e

    async def authenticateUser(self, email: str, password: str) -> Token:

        try:
            if not email:
                raise NoEmailorPasswordFound("Please enter valid email")
            if not password:
                raise NoEmailorPasswordFound("Please enter valid password")
            
            user_service = UserService(self._db)
            userPrivateModel = await user_service.getUserFromEmail(email, private=True)
            if not user_service.comparePassword(password, userPrivateModel.passwordHash):
                raise NotAuthorized("Invalid password")
            
            
            data = TokenModel(sub=userPrivateModel.sub, email=userPrivateModel.email)
            accessTokenExpires = timedelta(
                minutes=config.AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES
            )
            
            accessToken = self.encodeAccessToken(data, accessTokenExpires)
            return Token(
                accessToken=accessToken,
                tokenType="bearer",
            )
        except NotAuthorized:
            raise
        except NoEmailError:
            raise NotAuthorized("Invalid email or password") from None
        except LoginError:
            raise
        except Exception as e:
            raise LoginError(f"Error: {str(e)}") from e

    def encodeAccessToken(self, data: TokenModel, expireDelta: timedelta | None = None) -> str:
        to_encode = data.model_dump()
        if expireDelta:
            expire = datetime.now(timezone.utc) + expireDelta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)

        to_encode["exp"] = expire
        return jwt.encode(
            to_encode,
            config.AUTHENTICATION_SECRET_KEY,
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )

    def _decode_token_sub(self, token: str) -> str:
        """Validate JWT and return ``sub`` (user id). Raises CredentialException on failure."""
        try:
            payload = jwt.decode(
                token,
                config.AUTHENTICATION_SECRET_KEY,
                algorithms=[config.AUTHENTICATION_ALGORITHM],
            )
            user_id = payload.get("sub")
            if not user_id:
                raise CredentialException()
        except InvalidTokenError:
            raise CredentialException()
        return str(user_id)

    async def decodeAccessToken(self, token: Annotated[str, Depends(OAUTH2_SCHEME)]) -> UserModel:
        user_id = str(self._decode_token_sub(token))
        user_service = UserService(self._db)
        return await user_service.getUserFromUserId(user_id)
    
