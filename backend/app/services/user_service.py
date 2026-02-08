from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.security import get_password_hash
from backend.app.models.user import User, UserRole


def create_user(db: Session, username: str, password: str, role: UserRole) -> User:
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        username=username,
        password_hash=get_password_hash(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_default_admin(db: Session, username: str, password: str) -> None:
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if admin:
        return
    create_user(db, username=username, password=password, role=UserRole.ADMIN)
