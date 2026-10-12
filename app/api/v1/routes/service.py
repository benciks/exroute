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

    if intent.return_to_start:
      return await plan_destination_return(intent) if intent.end else await plan_generated_loop(intent)

    return await plan_a_to_b(intent)

async def plan_a_to_b(intent: RouteIntent):
    if intent.end is None: return
    start = geocode(intent.start)
    end = geocode(intent.end, start.lon, start.lat)

    points = [start]

    for stop in intent.stops:
      if stop.resolution != "exact_place":
        continue
      if stop.leg not in ("outbound", "whole_route"):
        continue

      waypoint = geocode(stop.request, start.lon, start.lat)
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

async def plan_destination_return(intent: RouteIntent):
  return

async def plan_generated_loop(intent: RouteIntent):
  return
