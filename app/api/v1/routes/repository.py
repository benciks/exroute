
from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

class RouteRepository:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session
