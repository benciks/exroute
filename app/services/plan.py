import asyncio
import random
from collections.abc import Sequence

from fastapi import HTTPException
from pydantic import BaseModel

from app.api.v1.routes.schemas import HeadingEnum, IntentTarget, RouteIntent, StopPositionEnum, StopSchema, TargetValueEnum
from app.core.exceptions import NoRouteFoundException, UnclearRequestException
from app.core.logging import get_logger
from app.services.geocode import Coordinates, Place, SearchArea, distance_km, geocode
from app.services.llm import pick_pois
from app.services.places import search_along_route
from app.services.valhalla import RouteOptions, round_trip, route
from app.utils.geometry import haversine_km
from app.utils.poi import ProjectPoi, filter_pois_by_position, project_pois_to_route, route_progress_km, route_segments
from app.utils.polyline import encode_shape, join_legs

logger = get_logger(__name__)

# How far off the route a discovered stop may be
POI_CORRIDOR_KM = 10
# Each segment is one Geoapify request per stop returning at most 20 places
POI_SEGMENT_KM = 25
# Caps requests per stop on long routes, the segments get longer instead
MAX_POI_SEGMENTS = 4
# Discovered stops closer than this read as one place on the map
MIN_POI_SPACING_KM = 1
# Loop size when the rider gave no distance or duration
DEFAULT_LOOP_TARGET = IntentTarget(value=150, unit=TargetValueEnum.Km)
HEADING_BEARINGS = {
  HeadingEnum.North: 0,
  HeadingEnum.NorthEast: 45,
  HeadingEnum.East: 90,
  HeadingEnum.SouthEast: 135,
  HeadingEnum.South: 180,
  HeadingEnum.SouthWest: 225,
  HeadingEnum.West: 270,
  HeadingEnum.NorthWest: 315,
}
HEADING_JITTER_DEG = 20
# A named stop may make the trip at most this many times longer than riding straight
# there, in straight-line distance. Rules out namesakes far away from the trip
STOP_DETOUR_FACTOR = 2.0
# ...plus this much, so stops just off a short trip are still accepted
STOP_SLACK_KM = 20
# Rough reach of a loop per minute of a duration target
LOOP_KM_PER_MIN = 1.0

class PlanResult(BaseModel):
  distance_km: float
  duration_min: float
  polyline: str
  waypoints: list[Place]

async def plan_a_to_b(instructions: str, intent: RouteIntent) -> PlanResult:
  if intent.end is None:
    # Without a destination or a loop there is nothing to plan, e.g. "Tell me a joke"
    raise UnclearRequestException("Where should the route go? Name a destination, or ask for a loop")

  start = await geocode(intent.start)
  end = await geocode(intent.end, start.lon, start.lat)

  exact_stops = [
    stop for stop in intent.stops
    if stop.resolution == "exact_place" and stop.leg != "return"
  ]
  exact = await geocode_stops(exact_stops, start, on_the_way(start, end), [start, end])

  opts = route_options(intent)
  points = [start, *exact, end]
  routed = await route(points, opts)

  discover = [
    stop for stop in intent.stops
    if stop.resolution == "discover" and stop.leg != "return"
  ]
  shape = join_legs(routed.leg_shapes)
  pois = await discover_pois(instructions, discover, shape)
  if pois:
    # Order every intermediate stop by how far along the baseline route it lies
    middle = sorted([*exact, *pois], key=lambda p: route_progress_km(shape, p))
    refined_points = [start, *middle, end]
    try:
      routed = await route(refined_points, opts)
      points = refined_points
    except Exception as e:
      if any(stop.priority == "required" for stop in discover): raise
      logger.warning(f"Refined route failed, keeping baseline: {e}")

  return PlanResult(
    distance_km=routed.distance_km,
    duration_min=routed.duration_min,
    polyline=encode_shape(join_legs(routed.leg_shapes)),
    waypoints=points,
  )

# An explicit "A to B and back" itinerary, routed with plain /route so it pays
# none of the round trip overlap penalties
async def plan_destination_return(instructions: str, intent: RouteIntent) -> PlanResult:
  if intent.end is None:
    raise NoRouteFoundException("A return trip needs a destination")

  start = await geocode(intent.start)

  outbound_stops = [
    stop for stop in intent.stops
    if stop.resolution == "exact_place" and stop.leg != "return"
  ]
  return_stops = [
    stop for stop in intent.stops
    if stop.resolution == "exact_place" and stop.leg == "return"
  ]
  end = await geocode(intent.end, start.lon, start.lat)
  # Stops on the way back are looked up around the destination
  outbound, back = await asyncio.gather(
    geocode_stops(outbound_stops, start, on_the_way(start, end), [start, end]),
    geocode_stops(return_stops, end, on_the_way(start, end), [start, end]),
  )

  opts = route_options(intent)
  points = [start, *outbound, end, *back, start]
  # A break at the destination splits the trip into exactly two legs: there and back
  routed = await route(points, opts, frozenset({len(outbound) + 1}))

  outbound_discover = [
    stop for stop in intent.stops
    if stop.resolution == "discover" and stop.leg != "return"
  ]
  return_discover = [
    stop for stop in intent.stops
    if stop.resolution == "discover" and stop.leg == "return"
  ]
  outbound_shape = join_legs(routed.leg_shapes[:1])
  return_shape = join_legs(routed.leg_shapes[1:])
  outbound_pois, return_pois = await asyncio.gather(
    discover_pois(instructions, outbound_discover, outbound_shape),
    discover_pois(instructions, return_discover, return_shape),
  )
  if outbound_pois or return_pois:
    outbound_middle = sorted([*outbound, *outbound_pois], key=lambda p: route_progress_km(outbound_shape, p))
    return_middle = sorted([*back, *return_pois], key=lambda p: route_progress_km(return_shape, p))
    refined_points = [start, *outbound_middle, end, *return_middle, start]
    try:
      routed = await route(refined_points, opts, frozenset({len(outbound_middle) + 1}))
      points = refined_points
    except Exception as e:
      if any(stop.priority == "required" for stop in [*outbound_discover, *return_discover]): raise
      logger.warning(f"Refined route failed, keeping baseline: {e}")

  return PlanResult(
    distance_km=routed.distance_km,
    duration_min=routed.duration_min,
    polyline=encode_shape(join_legs(routed.leg_shapes)),
    # The closing start is needed for routing but would duplicate the first waypoint
    waypoints=points[:-1],
  )

async def plan_generated_loop(instructions: str, intent: RouteIntent) -> PlanResult:
  start = await geocode(intent.start)
  target = intent.target or DEFAULT_LOOP_TARGET
  exact = await geocode_stops(
    [stop for stop in intent.stops if stop.resolution == "exact_place"],
    start,
    within_loop(start, target),
    [start],
  )

  opts = route_options(intent)
  # Reused for the refined call so Valhalla explores the same loop candidates
  seed = loop_seed(intent.heading)
  # Valhalla generates the loop's anchors itself, only the rider's own stops are sent
  points = [start, *exact]
  routed = await round_trip(points, target, opts, seed)

  discover = [stop for stop in intent.stops if stop.resolution == "discover"]
  shape = join_legs(routed.leg_shapes)
  pois = await discover_pois(instructions, discover, shape)
  if pois:
    middle = sorted([*exact, *pois], key=lambda p: route_progress_km(shape, p))
    refined_points = [start, *middle]
    try:
      routed = await round_trip(refined_points, target, opts, seed)
      points = refined_points
    except Exception as e:
      if any(stop.priority == "required" for stop in discover): raise
      logger.warning(f"Refined loop failed, keeping baseline: {e}")

  return PlanResult(
    distance_km=routed.distance_km,
    duration_min=routed.duration_min,
    polyline=encode_shape(join_legs(routed.leg_shapes)),
    waypoints=points,
  )

def loop_seed(heading: HeadingEnum | None) -> int:
  if heading is None:
    return random.randrange(0x100000000)
  # Valhalla points the first anchor of a loop without vias at seed % 360 degrees. The jitter
  # varies the loop between requests while staying within the heading's 45 degree sector
  bearing = (HEADING_BEARINGS[heading] + random.randint(-HEADING_JITTER_DEG, HEADING_JITTER_DEG)) % 360
  return random.randrange(0x100000000 // 360) * 360 + bearing

def route_options(intent: RouteIntent) -> RouteOptions:
  return RouteOptions(
    curvature=intent.curvature,
    avoid_motorways=intent.avoid_motorways,
    avoid_tolls=intent.avoid_tolls,
  )

def on_the_way(a: Coordinates, b: Coordinates) -> SearchArea:
  """Where a trip from a to b can pass a stop without a huge detour.

  The places whose detour stays within the limit form an ellipse around a and b, the
  circle around its center with half the limit as radius contains all of it.
  """
  limit = STOP_DETOUR_FACTOR * distance_km(a, b) + STOP_SLACK_KM
  return SearchArea(lon=(a.lon + b.lon) / 2, lat=(a.lat + b.lat) / 2, radius_km=limit / 2)

def within_loop(start: Coordinates, target: IntentTarget) -> SearchArea:
  """Where a loop of the target size can reach, at most half its length from the start."""
  length = target.value if target.unit == TargetValueEnum.Km else target.value * LOOP_KM_PER_MIN
  return SearchArea(lon=start.lon, lat=start.lat, radius_km=length / 2 + STOP_SLACK_KM)

async def geocode_stops(
  stops: list[StopSchema],
  near: Coordinates,
  area: SearchArea | None = None,
  away_from: Sequence[Coordinates] = (),
) -> list[Place]:
  results = await asyncio.gather(
    *(geocode(stop.request, near.lon, near.lat, area, away_from) for stop in stops),
    return_exceptions=True
  )

  places: list[Place] = []
  for stop, result in zip(stops, results):
    if isinstance(result, BaseException):
      if stop.priority == "required" or not isinstance(result, HTTPException): raise result
      logger.warning(f"Optional stop could not be geocoded: {stop.request}")
      continue
    places.append(result)
  return places

async def discover_pois(
  instructions: str,
  stops: list[StopSchema],
  shape: list[tuple[float, float]]
) -> list[Place]:
  if not stops:
    return []

  segments = route_segments(shape, POI_SEGMENT_KM, MAX_POI_SEGMENTS)
  if not segments:
    return []

  found = await asyncio.gather(
    *(search_along_route(stop.categories, segments, POI_CORRIDOR_KM) for stop in stops),
    return_exceptions=True
  )

  eligible: list[list[ProjectPoi]] = []
  for stop, candidates in zip(stops, found):
    if isinstance(candidates, BaseException):
      if stop.priority == "required": raise candidates
      logger.warning(f"POI search failed for '{stop.request}': {candidates}")
      candidates = []
    projected = project_pois_to_route(shape, candidates)
    stop_eligible = filter_pois_by_position(projected, stop.position, POI_CORRIDOR_KM, stop.max_detour_km)
    # A stop anywhere along the route beats no stop when the position is too strict
    if not stop_eligible:
      stop_eligible = filter_pois_by_position(projected, StopPositionEnum.Any, POI_CORRIDOR_KM, stop.max_detour_km)
    eligible.append(stop_eligible)

  # Without the LLM's ranking the places closest to the route are the safest pick
  ranked = [sorted(candidates, key=lambda poi: poi.distance_to_route_km) for candidates in eligible]
  if any(eligible):
    try:
      picks = await pick_pois(instructions, stops, eligible)
      ranked = [[] for _ in stops]
      for pick in picks:
        if not 0 <= pick.stop_index < len(stops): continue
        candidates = eligible[pick.stop_index]
        ranked[pick.stop_index] = [candidates[id] for id in pick.candidate_ids if 0 <= id < len(candidates)]
    except Exception as e:
      logger.warning(f"POI ranking failed, using the places closest to the route: {e}")

  selected: list[Place] = []
  for index, stop in enumerate(stops):
    picked: list[Place] = []
    for poi in ranked[index]:
      if len(picked) == (stop.count or 1): break
      too_close = any(
        p.name == poi.name or haversine_km((p.lat, p.lon), (poi.lat, poi.lon)) < MIN_POI_SPACING_KM
        for p in [*selected, *picked]
      )
      if too_close: continue
      picked.append(Place(lat=poi.lat, lon=poi.lon, name=poi.name))

    if not picked and stop.priority == "required":
      raise NoRouteFoundException(f"Could not find a suitable stop for: {stop.request}")
    logger.info(f"Selected {[p.name for p in picked]} for '{stop.request}'")
    selected.extend(picked)

  return selected
