from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.logging import get_logger
from app.core.security import create_access_token, verify_password
from app.api.v1.users.models import User
from app.api.v1.users.repository import UserRepository
from app.api.v1.users.schemas import LoginData, Token, UserCreate

logger = get_logger(__name__)

class UserService:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session
    self.repository = UserRepository(session)

  async def create_user(self, user_data: UserCreate) -> User:
    return await self.repository.create(user_data)

  async def authenticate(self, login_data: LoginData) -> Token:
    user = await self.repository.get_by_email(login_data.email)

    if not user or not verify_password(
      login_data.password, user.hashed_password
    ):
      raise UnauthorizedException(detail="Incorrect email or password")

    access_token = create_access_token(
      data={"sub": str(user.id)},
      expires_delta=timedelta(minutes=settings.JWT_EXPIRATION),
    )

    logger.info(f"User authenticated: {user.email}")
    return Token(access_token=access_token)

  async def get_user(self, user_id: UUID) -> User:
    return await self.repository.get_by_id(user_id)
  