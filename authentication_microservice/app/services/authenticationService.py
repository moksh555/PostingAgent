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
from app.errorsHandler.baseError import AuthenticationError
from app.errorsHandler.userError import NoEmailError
from fastapi import Depends #type: ignore
from configurations.config import config
from fastapi.security import OAuth2PasswordBearer #type: ignore
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
import jwt #type:ignore
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError  # type: ignore

from app.models.userModel import UserModel

class AuthenticationService:
    OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")

    def __init__(self, db: PostgreSQLRepository) -> None:
        self._db = db

    async def loginUser(self, userPayload: LoginRequest) -> (Token, Token):

        try:
            email = userPayload.email.strip().lower()
            password = userPayload.password

            accessToken, refreshToken = await self.authenticateUser(email, password)
            return (accessToken, refreshToken)
        except LoginError as e:
            raise
        except Exception as e:
            raise LoginError(str(e)) from e
    
    async def registerUser(self, userPayload: RegisterRequest) -> (Token, Token):
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
            access_token = self._encodeAccessToken(data, access_token_expires)
            refresh_token_expires = timedelta(
                days=config.AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS
            )
            refresh_token = self._encodeRefreshToken(data, refresh_token_expires)
            accessToken = Token(
                accessToken=access_token,
                tokenType="ACCESS_TOKEN",
            )
            refreshToken = Token(
                accessToken=refresh_token,
                tokenType="REFRESH_TOKEN",
            )
            return (accessToken, refreshToken)
        except Exception as e:
            raise RegisterError(str(e)) from e

    async def authenticateUser(self, email: str, password: str) -> (Token, Token):

        try:
            if not email:
                raise NoEmailorPasswordFound("Please enter valid email")
            if not password:
                raise NoEmailorPasswordFound("Please enter valid password")
            
            user_service = UserService(self._db)
            userPrivateModel = await user_service.getUserFromEmail(email, private=True)
            if not user_service._comparePassword(password, userPrivateModel.passwordHash):
                raise NotAuthorized("Invalid password")
            
            
            data = TokenModel(sub=userPrivateModel.sub, email=userPrivateModel.email)
            accessTokenExpires = timedelta(
                minutes=config.AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES
            )
            refreshTokenExpires = timedelta(
                days=config.AUTHENTICATION_REFRESH_TOKEN_EXPIRE_DAYS,
            )
            
            accessToken = self._encodeAccessToken(data, accessTokenExpires)
            refreshToken = self._encodeRefreshToken(data, refreshTokenExpires)
            return (Token(
                accessToken=accessToken,
                tokenType="ACCESS_TOKEN",
            ), Token(
                accessToken=refreshToken,
                tokenType="REFRESH_TOKEN",
            ))
        except NotAuthorized:
            raise
        except NoEmailError:
            raise NotAuthorized("Invalid email or password") from None
        except LoginError:
            raise
        except Exception as e:
            raise LoginError(f"Error: {str(e)}") from e

    def _encodeAccessToken(self, data: TokenModel, expireDelta: timedelta | None = None) -> str:
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
    
    def _encodeRefreshToken(self, data: TokenModel, expireDelta: timedelta | None = None) -> str:
        to_encode = data.model_dump()
        if expireDelta:
            expire = datetime.now(timezone.utc) + expireDelta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=7)

        to_encode["exp"] = expire
        return jwt.encode(
            to_encode,
            config.AUTHENTICATION_REFRESH_SECRET_KEY,
            algorithm=config.AUTHENTICATION_ALGORITHM,
        )
    
    def generateAccessTokenFromRefreshToken(self, refreshToken: str) -> Token:
        try:
            if not refreshToken:
                raise CredentialException("Refresh token is required")
            try:
                payload = jwt.decode(
                    refreshToken,
                    config.AUTHENTICATION_REFRESH_SECRET_KEY,
                    algorithms=[config.AUTHENTICATION_ALGORITHM],
                )
            except ExpiredSignatureError as e:
                raise NotAuthorized("Refresh token expired") from e
            except InvalidTokenError:
                raise CredentialException()

            user_id = payload.get("sub")
            if not user_id:
                raise CredentialException()

            data = TokenModel(sub=payload.get("sub"), email=payload.get("email"))
            expireDelta = timedelta(
                minutes=config.AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES
            )
            accessToken = self._encodeAccessToken(data, expireDelta)
            return Token(
                accessToken=accessToken,
                tokenType="ACCESS_TOKEN",
            )
        except (CredentialException, NotAuthorized):
            raise
        except Exception as e:
            raise CredentialException(str(e)) from e

    def _decode_access_token_payload(self, token: str) -> dict[str, Any]:
        """Decode and validate access JWT. Lets ``ExpiredSignatureError`` propagate (e.g. for refresh). Maps other JWT errors to ``CredentialException``."""
        try:
            payload = jwt.decode(
                token,
                config.AUTHENTICATION_SECRET_KEY,
                algorithms=[config.AUTHENTICATION_ALGORITHM],
            )
        except ExpiredSignatureError:
            raise
        except InvalidTokenError:
            raise CredentialException()

        if not payload.get("sub"):
            raise CredentialException()
        return payload

    async def decodeAccessToken(self, token: Annotated[str, Depends(OAUTH2_SCHEME)]) -> UserModel:
        """Bearer dependency: expired or invalid access token → ``CredentialException`` (no refresh here)."""
        try:
            payload = self._decode_access_token_payload(token)
            user_service = UserService(self._db)
            return await user_service.getUserFromUserId(str(payload["sub"]))
        except ExpiredSignatureError:
            raise CredentialException("Access token expired") from None
        except CredentialException:
            raise
        except AuthenticationError:
            raise
        except Exception as e:
            raise CredentialException(str(e)) from e

    async def getUserFromAccessToken(self, accessToken: str, refreshToken: str) -> UserModel:
        """
        Load user from access JWT. On **expiry only**, exchange ``refreshToken`` for a new access token and retry.
        Other failures (bad signature, malformed JWT, missing ``sub``) → ``CredentialException`` without refresh.
        """
        user_service = UserService(self._db)
        try:
            payload = self._decode_access_token_payload(accessToken)
            return await user_service.getUserFromUserId(str(payload["sub"]))
        except ExpiredSignatureError:
            new_access = self.generateAccessTokenFromRefreshToken(refreshToken)
            return await self.decodeAccessToken(new_access.accessToken)
        except CredentialException:
            raise
        except AuthenticationError:
            raise
