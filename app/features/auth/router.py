from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.features.auth.service import AuthConflictError, LoginFailedError, login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
    responses={
        409: {"description": "Username, email или телефон уже заняты"},
        422: {"description": "Ошибка валидации"},
    },
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await register_user(session, payload)
    except AuthConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход",
    responses={401: {"description": "Неверный contact или пароль"}},
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await login_user(session, payload)
    except LoginFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        ) from exc
