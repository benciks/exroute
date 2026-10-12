import asyncio

from fastapi import HTTPException
from pydantic import BaseModel

from app.api.v1.routes.schemas import RouteIntent, StopSchema
from app.core.exceptions import NoRouteFoundException
from app.core.logging import get_logger
from app.services.geocode import Coordinates, Place, geocode, reverse_geocode
from app.services.llm import RouteSample, suggest_pois
from app.services.valhalla import RouteOptions, route
from app.utils.poi import PoiCandidate, filter_pois_by_position, project_pois_to_route, route_progress_km, sample_route
from app.utils.polyline import encode_shape, join_legs

logger = get_logger(__name__)

# How far off the route a discovered stop may be
POI_CORRIDOR_KM = 10
# Search radius around the route sample the LLM placed the POI near
POI_SEARCH_RADIUS_KM = 15
# sample_route spaces points ~8 km apart up to this cap, more samples = more local suggestions
MAX_ROUTE_SAMPLES = 12

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

  opts = RouteOptions(
    curvature=intent.curvature,
    avoid_motorways=intent.avoid_motorways,
    avoid_tolls=intent.avoid_tolls,
  )
  points = [start, *exact, end]
  routed = await route(points, opts)

  discover = [
    stop for stop in intent.stops
    if stop.resolution == "discover" and stop.leg != "return"
  ]
  if discover:
    shape = join_legs(routed.leg_shapes)
    pois = await discover_pois(instructions, discover, shape)

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

  suggestions = [
    suggestion for suggestion in await suggest_pois(instructions, stops, samples, POI_CORRIDOR_KM)
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

    picked: list[Place] = []
    for poi in eligible:
      if len(picked) == (stop.count or 1): break
      if any(p.name == poi.name for p in [*selected, *picked]): continue
      picked.append(Place(lat=poi.lat, lon=poi.lon, name=poi.name))

    if not picked and stop.priority == "required":
      raise NoRouteFoundException(f"Could not find a suitable stop for: {stop.request}")
    logger.info(f"Selected {[p.name for p in picked]} for '{stop.request}'")
    selected.extend(picked)

  return selected

async def plan_destination_return(instructions: str, intent: RouteIntent):
  return

async def plan_generated_loop(instructions: str, intent: RouteIntent):
  return
