from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import settings

pwd_context = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain: str, hashed: str) -> bool:
  return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
  return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
  to_encode = data.copy()
  expire = datetime.now(timezone.utc) + (
    expires_delta or timedelta(minutes=settings.JWT_EXPIRATION)
  )
  to_encode.update({"exp": expire})
  return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
  """"Dependency to get current authenticated user."""
  credentials_exception = HTTPException(
    status_code = status.HTTP_401_UNAUTHORIZED,
    detail="Invalid authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
  )

  try:
    payload = jwt.decode(
      token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    user_id: str | None = payload.get("sub")
    if user_id is None:
      raise credentials_exception
  except JWTError:
    raise credentials_exception

  # Import here to avoid circular imports
  from app.core.db import get_session
  from app.api.v1.users.service import UserService

  async for session in get_session():
    user = await UserService(session).get_user(UUID(user_id))
    if user is None:
      raise credentials_exception
    return user
