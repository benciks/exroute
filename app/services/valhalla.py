from app.api.v1.routes.schemas import CurvatureEnum, IntentTarget, TargetModeEnum, TargetValueEnum
from app.core.exceptions import NoRouteFoundException
from app.services.geocode import Coordinates
from pydantic import BaseModel
import httpx2
import random
from collections.abc import Sequence

from app.core.config import settings

class RouteOptions(BaseModel):
  curvature: CurvatureEnum | None = None
  avoid_motorways: bool | None = None
  avoid_tolls: bool | None = None

class TripSummary(BaseModel):
  length: float
  time: float

class TripLeg(BaseModel):
  shape: str

class Trip(BaseModel):
  summary: TripSummary
  legs: list[TripLeg]

class TripResult(BaseModel):
  trip: Trip

class RouteResult(BaseModel):
  distance_km: float
  duration_min: float
  leg_shapes: list[str]

curvature_to_scalar = {
  "low": 0.0,
  "medium": 0.4,
  "high": 0.8
}

REUSED_EDGE_RADIUS_METERS = 50
REUSED_EDGE_FACTOR = 8

def costing_options(opts: RouteOptions) -> dict[str, float]:
  costing_options = {}
  if opts.curvature:
    costing_options["use_curvature"] = curvature_to_scalar[opts.curvature] 

  if opts.avoid_motorways:
    costing_options["use_highways"] = 0.0
    costing_options["use_trunk"] = 0.0

  if opts.avoid_tolls:
    costing_options["use_tolls"] = 0.0 

  return costing_options

async def route(
    locations: Sequence[Coordinates],
    opts: RouteOptions,
    break_indexes: frozenset[int] = frozenset()
) -> RouteResult:
  url = settings.VALHALLA_URL + "/route"
  typed_locations = []

  # First, last and explicit ones are breaks, the others are "through" - pass without
  # a u-turn, "via" allows one and makes out-and-back spurs to every stop
  for idx, location in enumerate(locations):
    stop = idx == 0 or idx == len(locations) - 1 or idx in break_indexes

    typed_locations.append({
        "type": "break" if stop else "through",
        "lon": location.lon,
        "lat": location.lat
    })

  params = {
    "locations": typed_locations,
    "costing": "motorcycle",
    "costing_options": {
      "motorcycle": costing_options(opts)
    },
    "directions_options": {
      "units": "kilometers"
    },
    "format": "json"
  }
  async with httpx2.AsyncClient(timeout=30.0) as client:
    response = await client.post(url, json=params)
  response.raise_for_status()
  result = TripResult.model_validate(response.json())

  return RouteResult(
      distance_km = result.trip.summary.length,
      duration_min =  result.trip.summary.time / 60,
      leg_shapes = [
        leg.shape for leg in result.trip.legs
      ],
  )

async def round_trip(
    locations: Sequence[Coordinates],
    target: IntentTarget,
    opts: RouteOptions,
    seed: int | None = None
) -> RouteResult:
  if not locations: raise NoRouteFoundException("a round trip needs an origin")

  if seed is None:
    seed = random.randrange(0x100000000) 
  target_km = target.value if target.unit == TargetValueEnum.Km else target.value * 0.92

  candidates = 3
  if target_km < 100: candidates = 5
  if target_km >= 500: candidates = 2

  max_overlap = 0.005 if target_km < 100 else 0.02 

  params = {
    "locations": [{"lat": p.lat, "lon": p.lon} for p in locations],
    "costing": "motorcycle",
    "costing_options": {
      "motorcycle": costing_options(opts)
    },
    "directions_options": {
      "units": "kilometers"
    },
    "format": "json",
    "round_trip_options": {
      "overlap_radius": REUSED_EDGE_RADIUS_METERS,
      "max_overlap": max_overlap,
      "reuse_factor": REUSED_EDGE_FACTOR,
      "candidates": candidates,
      "seed": seed,
      "prefer_under": target.mode == TargetModeEnum.Under,
      "prefer_at_least": target.mode == TargetModeEnum.At_least
    }
  }

  if target.unit == TargetValueEnum.Km:
    params["target_distance"] = target.value
  else:
    params["target_time"] = target.value

  url = settings.VALHALLA_URL + "/round_trip"
  async with httpx2.AsyncClient(timeout=120.0) as client:
    response = await client.post(url, json=params)
  response.raise_for_status()
  result = TripResult.model_validate(response.json())

  return RouteResult(
      distance_km = result.trip.summary.length,
      duration_min = result.trip.summary.time / 60,
      leg_shapes = [
          leg.shape for leg in result.trip.legs
      ],
  )