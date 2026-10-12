import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.models import Route
from app.core.exceptions import NotFoundException
from app.core.logging import get_logger
from app.services.plan import PlanResult

logger = get_logger(__name__)

class RouteRepository:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def create(self, user_id: uuid.UUID, instructions: str, result: PlanResult) -> Route:
    route = Route(
      user_id = user_id,
      instructions = instructions,
      distance_km = result.distance_km,
      duration_min = result.duration_min,
      polyline = result.polyline,
      waypoints = [waypoint.model_dump() for waypoint in result.waypoints],
    )
    self.session.add(route)
    await self.session.commit()
    await self.session.refresh(route)

    logger.info(f"Created route: {route.id}")
    return route

  # Scoped to the owner, other users' routes look like they don't exist
  async def get_by_id(self, route_id: uuid.UUID, user_id: uuid.UUID) -> Route:
    query = select(Route).where(Route.id == route_id, Route.user_id == user_id)
    result = await self.session.execute(query)
    route = result.scalar_one_or_none()

    if not route:
      raise NotFoundException("Route not found")

    return route
