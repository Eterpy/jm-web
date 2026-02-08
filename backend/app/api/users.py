from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_admin
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.user import JmCredentialUpdateRequest, UserCreateRequest, UserDeleteResponse, UserOut
from backend.app.services.crypto_service import encrypt_text
from backend.app.services.user_service import create_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserOut.model_validate(user) for user in users]


@router.post("", response_model=UserOut)
def create_user_api(
    payload: UserCreateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = create_user(db, username=payload.username, password=payload.password, role=payload.role)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", response_model=UserDeleteResponse)
def delete_user_api(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserDeleteResponse:
    if admin.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot delete self")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()
    return UserDeleteResponse(deleted=True)


@router.put("/me/jm-credentials", response_model=UserOut)
def update_my_jm_credentials(
    payload: JmCredentialUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.query(User).filter(User.id == current_user.id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.jm_username = payload.jm_username
    user.jm_password_encrypted = encrypt_text(payload.jm_password)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
