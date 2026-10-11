import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.core.logging import get_logger
from app.core.security import get_password_hash
from app.api.v1.users.models import User
from app.api.v1.users.schemas import UserCreate

logger = get_logger(__name__)

class UserRepository:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def create(self, user_data: UserCreate) -> User:
    existing_user = await self.get_by_email(user_data.email)
    if existing_user:
      raise AlreadyExistsException("Email already registered")

    user = User(
      email = user_data.email, hashed_password=get_password_hash(user_data.password)
    )
    self.session.add(user)
    await self.session.commit()
    await self.session.refresh(user)

    logger.info(f"Created user: {user.email}")
    return user

  async def get_by_id(self, user_id: uuid.UUID) -> User | None:
    query = select(User).where(User.id == user_id)
    result = await self.session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
      raise NotFoundException("User not found")

    return user

  async def get_by_email(self, email: str) -> User | None:
    query = select(User).where(User.email == email)
    result = await self.session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
      raise NotFoundException("User not found")
    return user