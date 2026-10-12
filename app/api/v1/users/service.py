import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, UnauthorizedException
from app.core.logging import get_logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.api.v1.users.models import User
from app.api.v1.users.repository import UserRepository
from app.api.v1.users.schemas import LoginData, Token, UserCreate

logger = get_logger(__name__)

class UserService:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session
    self.repository = UserRepository(session)

  async def create_user(self, user_data: UserCreate) -> User:
    if await self.repository.get_by_email(user_data.email):
      raise AlreadyExistsException("Email already registered")

    # Argon2 is deliberately slow CPU work, a thread keeps it off the event loop
    hashed_password = await asyncio.to_thread(get_password_hash, user_data.password)
    return await self.repository.create(user_data.email, hashed_password)

  async def authenticate(self, login_data: LoginData) -> Token:
    user = await self.repository.get_by_email(login_data.email)

    if not user or not await asyncio.to_thread(
      verify_password, login_data.password, user.hashed_password
    ):
      raise UnauthorizedException(detail="Incorrect email or password")

    logger.info(f"User authenticated: {user.id}")
    return Token(access_token=create_access_token(str(user.id)))

  async def get_user(self, user_id: UUID) -> User | None:
    return await self.repository.get_by_id(user_id)
