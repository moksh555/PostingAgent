from app.models.userModel import (
    UserModel, 
    CreateUserModel, 
    UserPrivateModel
)
from app.repository.postgreSql import PostgreSQLRepository
from app.errorsHandler.databaseError import (
    FailedToGetUserFromUserId,
    FailedToCreateUser,
    FailedToGetUserFromEmail
    )
from app.errorsHandler.userError import (
    NoUserIdError,
    NoEmailError
    )

class UserRepository:
    def __init__(self, db: PostgreSQLRepository):
        self.db = db

    async def getUserFromUserId(self, userId: str) -> UserModel:
        try:
            user = await self.db.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                userId,
            )
            if not user:
                raise NoUserIdError("User not found in the database")
            
            data = UserModel(
                email=user["email"],
                sub=str(user["user_id"]),
                userFirstName=user["first_name"],
                userLastName=user["last_name"],
                phoneNumber=user["phone_number"],
                dateOfBirth=user["date_of_birth"],
                createdAt=user["created_at"],
                isActive=user["is_active"],
                subscriptionType=user["subscription_type"],
            )
            return data
        except NoUserIdError:
            raise
        except Exception as e:
            raise FailedToGetUserFromUserId(f"Failed to get user from user id: {e}") from e
    
    async def createUser(self, user: CreateUserModel) -> UserModel:
        try:
            await self.db.execute(
                "INSERT INTO users (email, user_id, first_name, last_name, phone_number, date_of_birth, created_at, is_active, password_hash, subscription_type) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                user.email,
                user.sub,
                user.userFirstName,
                user.userLastName,
                user.phoneNumber,
                user.dateOfBirth,
                user.createdAt,
                user.isActive,
                user.passwordHash,
                user.subscriptionType,
            )
            return UserModel(
                email=user.email,
                sub=user.sub,
                userFirstName=user.userFirstName,
                userLastName=user.userLastName,
                phoneNumber=user.phoneNumber,
                dateOfBirth=user.dateOfBirth,
                createdAt=user.createdAt,
                isActive=user.isActive,
                subscriptionType=user.subscriptionType,
            )
        except Exception as e:
            raise FailedToCreateUser(f"Failed to create user: {e}") from e

    async def getUserFromEmail(self, email: str) -> tuple[UserModel, UserPrivateModel]:
        try:
            user = await self.db.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email,
            )
            if not user:
                raise NoEmailError("User not found in the database")
            userPrivateModel = UserPrivateModel(
                email=user["email"],
                sub=str(user["user_id"]),
                userFirstName=user["first_name"],
                userLastName=user["last_name"],
                phoneNumber=user["phone_number"],
                dateOfBirth=user["date_of_birth"],
                createdAt=user["created_at"],
                isActive=user["is_active"],
                subscriptionType=user["subscription_type"],
                passwordHash=user["password_hash"],
            )
            userModel = UserModel(
                email=user["email"],
                sub=str(user["user_id"]),
                userFirstName=user["first_name"],
                userLastName=user["last_name"],
                phoneNumber=user["phone_number"],
                dateOfBirth=user["date_of_birth"],
                createdAt=user["created_at"],
                isActive=user["is_active"],
                subscriptionType=user["subscription_type"],
            )
            return (userModel, userPrivateModel)
        except NoEmailError:
            raise
        except Exception as e:
            raise FailedToGetUserFromEmail(f"Failed to get user from email: {e}") from e
