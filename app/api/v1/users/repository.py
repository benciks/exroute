import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException
from app.core.logging import get_logger
from app.api.v1.users.models import User

logger = get_logger(__name__)

class UserRepository:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def create(self, email: str, hashed_password: str) -> User:
    user = User(email=email, hashed_password=hashed_password)
    self.session.add(user)
    try:
      await self.session.commit()
    except IntegrityError:
      # Two registrations of one email raced past the existence check in the service
      await self.session.rollback()
      raise AlreadyExistsException("Email already registered") from None
    await self.session.refresh(user)

    logger.info(f"Created user: {user.id}")
    return user

  async def get_by_id(self, user_id: uuid.UUID) -> User | None:
    query = select(User).where(User.id == user_id)
    result = await self.session.execute(query)
    return result.scalar_one_or_none()

  async def get_by_email(self, email: str) -> User | None:
    query = select(User).where(User.email == email)
    result = await self.session.execute(query)
    return result.scalar_one_or_none()
