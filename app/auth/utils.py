import hashlib
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config.settings import settings
from ..logs.logger import logger

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MAX_BCRYPT_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    password_len = len(password_bytes)

    if password_len > MAX_BCRYPT_BYTES:
        logger.warning(
            f"Password exceeds {MAX_BCRYPT_BYTES} bytes ({password_len}), applying SHA-256 preprocessing"
        )
        processed = hashlib.sha256(password_bytes).hexdigest()
    else:
        processed = password

    return pwd_context.hash(processed)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')

    if pwd_context.verify(plain_password, hashed_password):
        return True

    if len(password_bytes) > MAX_BCRYPT_BYTES:
        processed = hashlib.sha256(password_bytes).hexdigest()
        return pwd_context.verify(processed, hashed_password)

    return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if not payload.get("sub"):
            return None
        try:
            if payload.get("exp") and int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
                return None
        except (ValueError, TypeError):
            return None
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def generate_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def get_password_strength(password: str) -> bool:
    if len(password) < 8:
        return False
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_upper and has_lower and has_digit
