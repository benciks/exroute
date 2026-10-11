from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.schemas import RouteCreate, RouteIntent
from app.services.llm import parse_intent
from app.services.geocode import geocode
from app.services.valhalla import RouteOptions, route

class RouteService:
  def __init__(self, session: AsyncSession) -> None:
    self.session = session

  async def create_route(self, route_data: RouteCreate):
    intent = parse_intent(route_data.instructions)

    if intent is None:
      return None

    # TODO: handle via exception when moved to dif function
    if not intent.end:
      return None

    # test geocoding
    start = geocode(intent.start)
    end = geocode(intent.end)

    points = [start]

    for stop in intent.stops:
      if stop.resolution != "exact_place":
        continue
      if stop.leg not in ("outbound", "whole_route"):
        continue

      waypoint = geocode(stop.request)
      points.append(waypoint)

    points.append(end)

    route_result = route(points, RouteOptions(
      curvature=intent.curvature,
      avoid_motorways=intent.avoid_motorways,
      avoid_tolls=intent.avoid_tolls,
    ))

    return {
      "intent": intent,
      "routing_result": route_result
    }

  # async def plan_a_to_b(intent: RouteIntent):
    # geocode star
    # geocode end
    # geocode waypoints
    # batch??
    # parse options
    # valhalla route - points and options
    # discover stops -> llm -> geocode - or mapbox right away?
    # insert waypoints on path
    # refine route - valhalla call
    # return
