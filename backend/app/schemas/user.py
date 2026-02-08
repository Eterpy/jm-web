from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.user import User
from backend.app.models.user import UserRole


class UserBase(BaseModel):
    username: str
    role: UserRole
    is_active: bool


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.USER


class UserDeleteResponse(BaseModel):
    deleted: bool


class JmCredentialUpdateRequest(BaseModel):
    jm_username: str = Field(min_length=1, max_length=128)
    jm_password: str = Field(min_length=1, max_length=256)


class UserMeOut(UserOut):
    jm_username: str | None = None
    jm_credential_bound: bool = False

    @classmethod
    def from_user(cls, user: User) -> "UserMeOut":
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            jm_username=user.jm_username,
            jm_credential_bound=bool(user.jm_username and user.jm_password_encrypted),
        )
