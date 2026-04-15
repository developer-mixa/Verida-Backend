from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_USER_ID
from app.core.models.user import User
from app.core.security import create_access_token, hash_password, verify_password
from app.features.auth.contact import login_contact_variants
from app.features.auth.schemas import LoginRequest, RegisterRequest, TokenResponse


class AuthConflictError(Exception):
    """Нарушение уникальности (username / email / телефон)."""

    def __init__(self, message: str = "Пользователь с такими данными уже существует") -> None:
        self.message = message
        super().__init__(message)


class LoginFailedError(Exception):
    """Неверный contact или пароль."""

    pass


async def register_user(session: AsyncSession, data: RegisterRequest) -> TokenResponse:
    user = User(
        username=data.username,
        email=data.email,
        number=data.phone,
        password_hash=hash_password(data.password),
        role_id=ROLE_USER_ID,
        is_verified=False,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AuthConflictError from None
    await session.refresh(user)
    token = create_access_token(subject=user.id, username=user.username)
    return TokenResponse(access_token=token)


async def login_user(session: AsyncSession, data: LoginRequest) -> TokenResponse:
    user = await _find_user_by_contact(session, data.contact)
    if user is None or not verify_password(data.password, user.password_hash):
        raise LoginFailedError
    token = create_access_token(subject=user.id, username=user.username)
    return TokenResponse(access_token=token)


async def _find_user_by_contact(session: AsyncSession, contact: str) -> User | None:
    username_key, email_lower, phone_digits = login_contact_variants(contact)
    if not username_key and email_lower is None and phone_digits is None:
        return None

    conditions = []
    if username_key:
        conditions.append(func.lower(User.username) == username_key)
    if email_lower is not None:
        conditions.append(func.lower(User.email) == email_lower)
    if phone_digits is not None:
        conditions.append(User.number == phone_digits)

    if not conditions:
        return None

    stmt = select(User).where(or_(*conditions)).limit(2)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    if len(rows) != 1:
        return None
    return rows[0]
