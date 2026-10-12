from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from collections.abc import AsyncGenerator

from app.core.config import settings

# Echo logs every statement with its parameters (emails, password hashes), so only in debug
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
  pass

async def get_session() -> AsyncGenerator[AsyncSession]:
  async with async_session() as session:
    yield session
