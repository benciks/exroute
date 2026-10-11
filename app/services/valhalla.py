from app.api.v1.routes.schemas import CurvatureEnum
from app.services.geocode import Coordinates
from pydantic import BaseModel
import httpx2

from app.core.config import settings

class RouteOptions(BaseModel):
  curvature: CurvatureEnum
  avoid_motorways: bool
  avoid_tolls: bool

class RouteResult(BaseModel):
  distance_km: float
  duration_min: float
  leg_shapes: list[str]

curvature_to_scalar = {
  "low": 0.0,
  "medium": 0.4,
  "high": 0.8
}

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

def route(
    locations: list[Coordinates],
    opts: RouteOptions
):
  url = settings.VALHALLA_URL + "/route"
  typed_locations = []

  # Asign types to coords - first and last should be break, other should be via
  for idx, location in enumerate(locations):
    first_or_last = idx == 0 or idx == len(locations) - 1

    typed_locations.append({
        "type": "break" if first_or_last else "via",
        "lon": location.lon,
        "lat": location.lat
    })

  params = {
    "locations": typed_locations,
    "costing": "motorcycle",
    "costing_options": {
      "motorcycle": costing_options(opts)
    },
    "direction_options": {
      "units": "kilometers"
    },
    "format": "json"
  }
  response = httpx2.post(url, json=params)
  response.raise_for_status()
  result = response.json()

  return {
      "distance_km": result["trip"]["summary"]["length"],
      "duration_min": result["trip"]["summary"]["time"] / 60,
      "leg_shapes": [
          leg["shape"] for leg in result["trip"]["legs"]
      ],
  }

  

  




