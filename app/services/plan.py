import asyncio
import random

from fastapi import HTTPException
from pydantic import BaseModel

from app.api.v1.routes.schemas import IntentTarget, RouteIntent, StopPositionEnum, StopSchema, TargetModeEnum, TargetValueEnum
from app.core.exceptions import NoRouteFoundException
from app.core.logging import get_logger
from app.services.geocode import Coordinates, Place, geocode, reverse_geocode
from app.services.llm import RouteSample, suggest_pois
from app.services.valhalla import RouteOptions, round_trip, route
from app.utils.geometry import haversine_km
from app.utils.poi import PoiCandidate, filter_pois_by_position, project_pois_to_route, route_progress_km, sample_route
from app.utils.polyline import encode_shape, join_legs

logger = get_logger(__name__)

# How far off the route a discovered stop may be
POI_CORRIDOR_KM = 10
# Search radius around the route sample the LLM placed the POI near
POI_SEARCH_RADIUS_KM = 15
# sample_route spaces points ~8 km apart up to this cap, more samples = more local suggestions
MAX_ROUTE_SAMPLES = 12
# Discovered stops closer than this read as one place on the map
MIN_POI_SPACING_KM = 1
# Loop size when the rider gave no distance or duration
DEFAULT_LOOP_TARGET = IntentTarget(value=150, unit=TargetValueEnum.Km, mode=TargetModeEnum.Open)

class PlanResult(BaseModel):
  distance_km: float
  duration_min: float
  polyline: str
  waypoints: list[Place]

async def plan_a_to_b(instructions: str, intent: RouteIntent) -> PlanResult:
  if intent.end is None:
    raise NoRouteFoundException("A one-way route needs an end destination")

  start = await geocode(intent.start)

  # End and exact stops are all focused around the start, so they can run at once
  exact_stops = [
    stop for stop in intent.stops
    if stop.resolution == "exact_place" and stop.leg != "return"
  ]
  end, exact = await asyncio.gather(
    geocode(intent.end, start.lon, start.lat),
    geocode_stops(exact_stops, start),
  )

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
  end, outbound = await asyncio.gather(
    geocode(intent.end, start.lon, start.lat),
    geocode_stops(outbound_stops, start),
  )
  # Stops on the way back are looked up around the destination
  back = await geocode_stops(return_stops, end)

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
  exact = await geocode_stops(
    [stop for stop in intent.stops if stop.resolution == "exact_place"],
    start,
  )

  opts = route_options(intent)
  target = intent.target or DEFAULT_LOOP_TARGET
  # Reused for the refined call so Valhalla explores the same loop candidates
  seed = random.randrange(0x100000000)
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

def route_options(intent: RouteIntent) -> RouteOptions:
  return RouteOptions(
    curvature=intent.curvature,
    avoid_motorways=intent.avoid_motorways,
    avoid_tolls=intent.avoid_tolls,
  )

async def geocode_stops(stops: list[StopSchema], near: Coordinates) -> list[Place]:
  results = await asyncio.gather(
    *(geocode(stop.request, near.lon, near.lat) for stop in stops),
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

  # Drop the endpoints, they are the start and end themselves
  sampled = sample_route(shape, MAX_ROUTE_SAMPLES)[1:-1]
  if not sampled:
    return []

  locations = await asyncio.gather(
    *(reverse_geocode(Coordinates(lat=lat, lon=lon)) for lat, lon in sampled),
    return_exceptions=True
  )
  samples = [
    RouteSample(
      index=index,
      progress_ratio=round((index + 1) / (len(sampled) + 1), 2),
      lat=lat,
      lon=lon,
      location=location if isinstance(location, str) else "unknown",
    )
    for index, ((lat, lon), location) in enumerate(zip(sampled, locations))
  ]

  try:
    suggested = await suggest_pois(instructions, stops, samples, POI_CORRIDOR_KM)
  except Exception as e:
    if any(stop.priority == "required" for stop in stops): raise
    logger.warning(f"POI suggestion failed, continuing without discovered stops: {e}")
    return []

  suggestions = [
    suggestion for suggestion in suggested
    if 0 <= suggestion.stop_index < len(stops) and 0 <= suggestion.sample_index < len(samples)
  ]

  places = await asyncio.gather(
    *(
      geocode(
        suggestion.search_query,
        samples[suggestion.sample_index].lon,
        samples[suggestion.sample_index].lat,
        layers="venue",
        radius_km=POI_SEARCH_RADIUS_KM
      )
      for suggestion in suggestions
    ),
    return_exceptions=True
  )

  candidates: dict[int, list[PoiCandidate]] = {index: [] for index in range(len(stops))}
  for suggestion, place in zip(suggestions, places):
    if isinstance(place, BaseException):
      logger.warning(f"Suggested POI could not be geocoded: {suggestion.name} ({place})")
      continue
    candidates[suggestion.stop_index].append(PoiCandidate(
      lat=place.lat,
      lon=place.lon,
      name=place.name,
      description=stops[suggestion.stop_index].request,
    ))

  selected: list[Place] = []
  for index, stop in enumerate(stops):
    projected = project_pois_to_route(shape, candidates[index])
    eligible = filter_pois_by_position(projected, stop.position, POI_CORRIDOR_KM, stop.max_detour_km)
    # A stop anywhere along the route beats no stop when the position is too strict
    if not eligible:
      eligible = filter_pois_by_position(projected, StopPositionEnum.Any, POI_CORRIDOR_KM, stop.max_detour_km)

    picked: list[Place] = []
    for poi in eligible:
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
