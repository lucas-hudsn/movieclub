from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings

_serializer = URLSafeSerializer(get_settings().secret_key, salt="session")

COOKIE_NAME = "movieclub_session"


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token)
        return int(data["uid"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def hash_password(password: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    try:
        PasswordHasher().verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False
