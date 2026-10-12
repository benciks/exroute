from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.db import async_session
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.api.v1.users.models import User
from app.api.v1.users.service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
  """Dependency to get current authenticated user."""
  subject = decode_access_token(token)
  try:
    user_id = UUID(subject) if subject else None
  except ValueError:
    user_id = None
  if user_id is None:
    raise UnauthorizedException("Invalid authentication credentials")

  # Own short session instead of the request one, which route planning would
  # otherwise keep checked out in an open transaction for the whole generation
  async with async_session() as session:
    user = await UserService(session).get_user(user_id)
  if user is None:
    raise UnauthorizedException("Invalid authentication credentials")
  return user
