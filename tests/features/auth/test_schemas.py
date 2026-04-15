import pytest
from pydantic import ValidationError

from app.features.auth.schemas import RegisterRequest


def test_register_requires_email_or_phone() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(username="validuser", email=None, phone=None, password="password1")
    assert "email" in str(exc.value).lower() or "телефон" in str(exc.value).lower() or "phone" in str(
        exc.value
    ).lower()


def test_register_accepts_email_only() -> None:
    r = RegisterRequest(
        username="userone",
        email="a@b.co",
        phone=None,
        password="password1",
    )
    assert r.username == "userone"
    assert r.email == "a@b.co"
    assert r.phone is None


def test_register_accepts_phone_only() -> None:
    r = RegisterRequest(
        username="usertwo",
        email=None,
        phone="+79991234567",
        password="password1",
    )
    assert r.phone == "79991234567"


def test_register_username_invalid() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username="ab", email="x@y.co", phone=None, password="password1")
