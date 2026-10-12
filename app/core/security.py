from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

pwd_context = PasswordHash.recommended()

def verify_password(plain: str, hashed: str) -> bool:
  return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
  return pwd_context.hash(password)

def create_access_token(subject: str) -> str:
  expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRATION)
  return jwt.encode({"sub": subject, "exp": expire}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> str | None:
  """Returns the token subject, or None when the token is invalid or expired."""
  try:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
  except jwt.InvalidTokenError:
    return None
  return payload.get("sub")
