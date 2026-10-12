import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.models import Route
from app.api.v1.routes.repository import RouteRepository
from app.api.v1.routes.schemas import RouteCreate
from app.services.llm import parse_intent
from app.services.plan import plan_a_to_b, plan_destination_return, plan_generated_loop
from app.utils.gpx import to_gpx

class RouteService:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session
    self.repository = RouteRepository(session)

  async def create_route(self, user_id: uuid.UUID, route_data: RouteCreate):
    instructions = route_data.instructions
    intent = await parse_intent(instructions)
    if intent.return_to_start:
      result = await plan_destination_return(instructions, intent) if intent.end else await plan_generated_loop(instructions, intent)
    else:
      result = await plan_a_to_b(instructions, intent)

    route = await self.repository.create(user_id, instructions, result)
    return {
      "id": route.id,
      "intent": intent,
      **result.model_dump()
    }

  async def list_routes(self, user_id: uuid.UUID) -> list[Route]:
    return await self.repository.list_for_user(user_id)

  async def get_gpx(self, route_id: uuid.UUID, user_id: uuid.UUID) -> str:
    route = await self.repository.get_by_id(route_id, user_id)
    return to_gpx(route.instructions, route.polyline, route.waypoints)
