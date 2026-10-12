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

# Valhalla is local and timeouts are set per request, one client reuses its connections
client = httpx2.AsyncClient()

curvature_to_scalar = {
  "low": 0.0,
  "medium": 0.4,
  "high": 0.8
}

def costing_options(opts: RouteOptions) -> dict[str, float]:
  costing_options = {}
  if opts.curvature:
    costing_options["use_curvature"] = curvature_to_scalar[opts.curvature] 

  # Motorcycle costing has no use_trunk, use_highways penalizes trunk roads at half weight
  if opts.avoid_motorways:
    costing_options["use_highways"] = 0.0

  if opts.avoid_tolls:
    costing_options["use_tolls"] = 0.0 

  return costing_options

async def route(
    locations: Sequence[Coordinates],
    opts: RouteOptions,
    break_indexes: frozenset[int] = frozenset()
) -> RouteResult:
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
  return await post_trip("/route", params, timeout=30.0)

async def round_trip(
    locations: Sequence[Coordinates],
    target: IntentTarget,
    opts: RouteOptions,
    seed: int | None = None
) -> RouteResult:
  if not locations: raise NoRouteFoundException("a round trip needs an origin")

  if seed is None:
    seed = random.randrange(0x100000000)

  # Valhalla sizes the search (candidates, overlap limits, reuse penalty) from the
  # target itself, the seed only rotates where it places the loop's anchors
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
      "seed": seed,
      "prefer_under": target.mode == TargetModeEnum.Under,
      "prefer_at_least": target.mode == TargetModeEnum.At_least
    }
  }

  if target.unit == TargetValueEnum.Km:
    params["target_distance"] = target.value
  else:
    params["target_time"] = target.value

  return await post_trip("/round_trip", params, timeout=120.0)

async def post_trip(path: str, params: dict, timeout: float) -> RouteResult:
  response = await client.post(settings.VALHALLA_URL + path, json=params, timeout=timeout)

  # A 4xx means Valhalla couldn't route this input, e.g. error 171 "No suitable
  # edges near location" for a point outside the tiles. Its reason is in the body.
  if response.is_client_error:
    error = response.json().get("error", response.text)
    raise NoRouteFoundException(f"Valhalla {path}: {error}")
  response.raise_for_status()
  result = TripResult.model_validate(response.json())

  return RouteResult(
      distance_km = result.trip.summary.length,
      duration_min = result.trip.summary.time / 60,
      leg_shapes = [
          leg.shape for leg in result.trip.legs
      ],
  )