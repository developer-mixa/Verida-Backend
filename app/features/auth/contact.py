"""Нормализация email/телефона и разбор строки входа (contact)."""

from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email

_DIGITS_ONLY = re.compile(r"^\+?[0-9\s\-()]{10,32}$")


def normalize_email(value: str) -> str:
    normalized = validate_email(value, check_deliverability=False).normalized.lower()
    return normalized


def normalize_phone(value: str) -> str:
    raw = value.strip()
    if not _DIGITS_ONLY.match(raw):
        raise ValueError("Неверный формат номера телефона")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Неверная длина номера телефона")
    return digits


def login_contact_variants(contact: str) -> tuple[str, str | None, str | None]:
    """Возвращает (username_lower, email_lower_or_none, phone_digits_or_none) для поиска пользователя."""
    c = contact.strip()
    if not c:
        return "", None, None

    username_key = c.lower()
    email_lower: str | None = None
    phone_digits: str | None = None

    if "@" in c:
        try:
            email_lower = normalize_email(c)
        except (EmailNotValidError, ValueError):
            email_lower = None

    try:
        phone_digits = normalize_phone(c)
    except ValueError:
        phone_digits = None

    return username_key, email_lower, phone_digits
