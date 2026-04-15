from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.auth.contact import normalize_email, normalize_phone

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.]{2,63}$")


class RegisterRequest(BaseModel):
    """Регистрация: username обязателен; нужен хотя бы один из email или phone."""

    username: str = Field(..., min_length=3, max_length=64)
    email: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("email", "phone", mode="before")
    @classmethod
    def strip_empty(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("username")
    @classmethod
    def username_normalized(cls, v: str) -> str:
        s = v.strip().lower()
        if not _USERNAME_RE.match(s):
            raise ValueError(
                "username: 3–64 символа, латиница в нижнем регистре, цифры, «_» и «.»; "
                "должен начинаться с буквы или цифры."
            )
        return s

    @field_validator("email")
    @classmethod
    def email_normalized(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_email(v)

    @field_validator("phone")
    @classmethod
    def phone_normalized(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_phone(v)

    @model_validator(mode="after")
    def require_email_or_phone(self) -> RegisterRequest:
        if self.email is None and self.phone is None:
            raise ValueError("Укажите email или телефон (можно оба).")
        return self


class LoginRequest(BaseModel):
    contact: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("contact")
    @classmethod
    def contact_stripped(cls, v: str) -> str:
        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
