import uuid

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password() -> None:
    h = hash_password("secret-password")
    assert verify_password("secret-password", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip() -> None:
    uid = uuid.uuid4()
    token = create_access_token(subject=uid, username="tester")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["username"] == "tester"
