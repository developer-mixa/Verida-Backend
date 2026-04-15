import pytest

from app.features.auth.contact import login_contact_variants, normalize_email, normalize_phone


def test_normalize_email_lowercase() -> None:
    assert normalize_email("User@Example.COM") == "user@example.com"


def test_normalize_phone_strips_non_digits() -> None:
    assert normalize_phone("+7 (916) 123-45-67") == "79161234567"


def test_normalize_phone_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_phone("not-a-phone")


def test_login_contact_variants_email() -> None:
    u, e, p = login_contact_variants("User@Mail.com")
    assert u == "user@mail.com"
    assert e == "user@mail.com"
    assert p is None


def test_login_contact_variants_phone() -> None:
    u, e, p = login_contact_variants("+79991234567")
    assert u == "+79991234567".lower()
    assert e is None
    assert p == "79991234567"


def test_login_contact_variants_username() -> None:
    u, e, p = login_contact_variants("MyUser_1")
    assert u == "myuser_1"
    assert e is None
    assert p is None
