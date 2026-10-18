import math

from pydantic import BaseModel

from app.api.v1.routes.schemas import StopPositionEnum
from app.services.geocode import Coordinates
from app.utils.geometry import haversine_km

class PoiCandidate(Coordinates):
  id: str
  name: str
  categories: list[str] = []

class Projection(BaseModel):
  progress_km: float
  distance_to_route_km: float

class ProjectPoi(PoiCandidate, Projection):
  progress_ratio: float

def project_pois_to_route(
  route: list[tuple[float, float]],
  candidates: list[PoiCandidate]
) -> list[ProjectPoi]:
  if len(route) < 2: return []
  cumulative = cumulative_distances(route)
  total_km = cumulative[-1] if cumulative else 0
  if total_km <= 0: return []

  results = []
  for candidate in candidates:
    projection = project_to_route(candidate, route, cumulative)
    results.append(ProjectPoi(
      **candidate.model_dump(),
      progress_km = projection.progress_km,
      progress_ratio = projection.progress_km / total_km,
      distance_to_route_km = projection.distance_to_route_km 
    ))

  return results

def filter_pois_by_position(
  candidates: list[ProjectPoi],
  position: StopPositionEnum,
  corridor_km: float,
  max_detour_km: float | None = None
):
  minimum = 0.10
  maximum = 0.90

  if position == StopPositionEnum.Early:
    minimum = 0.05
    maximum = 0.40
  elif position == StopPositionEnum.Middle:
    minimum = 0.25
    maximum = 0.75
  elif position == StopPositionEnum.Late:
    minimum = 0.60
    maximum = 0.95

  maximum_distance = corridor_km if max_detour_km is None else min(corridor_km, max_detour_km / 2)

  return [
    candidate for candidate in candidates
    if candidate.distance_to_route_km <= maximum_distance
    and minimum <= candidate.progress_ratio <= maximum
  ]

# Splits the route into equal segments of about segment_km, longer when that would
# exceed maximum. Each segment is resampled every step_km to keep the request small
def route_segments(
  route: list[tuple[float, float]],
  segment_km: float,
  maximum: int,
  step_km: float = 1
) -> list[list[tuple[float, float]]]:
  cumulative = cumulative_distances(route)
  total_km = cumulative[-1] if cumulative else 0
  if total_km <= 0: return []
  count = min(maximum, max(1, math.ceil(total_km / segment_km)))
  length_km = total_km / count
  steps = max(1, math.ceil(length_km / step_km))
  return [
    [
      point_at_distance(route, cumulative, length_km * (index + step / steps))
      for step in range(steps + 1)
    ]
    for index in range(count)
  ]

def route_distance_km(route: list[tuple[float, float]]) -> float:
  cumulative = cumulative_distances(route)
  return cumulative[-1] if cumulative else 0.0

def route_progress_km(
    route: list[tuple[float, float]],
    point: Coordinates,
) -> float:
  if len(route) < 2: return 0.0;
  return project_to_route(point, route, cumulative_distances(route)).progress_km

def cumulative_distances(route: list[tuple[float, float]]) -> list[float]:
  cumulative: list[float] = [0.0];
  i = 1
  while i < len(route):
    cumulative.append(cumulative[i - 1] + haversine_km(route[i - 1], route[i]))
    i += 1

  return cumulative

def point_at_distance(
  route: list[tuple[float, float]],
  cumulative: list[float],
  distance_km: float
) -> tuple[float, float]:
  i = 1
  while i < len(cumulative):
    if distance_km <= cumulative[i]:
      leg = cumulative[i] - cumulative[i - 1]
      fraction = 0 if leg <= 0 else (distance_km - cumulative[i - 1]) / leg
      return (
        route[i - 1][0] + (route[i][0] - route[i - 1][0]) * fraction,
        route[i - 1][1] + (route[i][1] - route[i - 1][1]) * fraction
      )
    i += 1

  return route[-1] if route else (0, 0)

def project_to_route(
  point: Coordinates,
  route: list[tuple[float, float]],
  cumulative: list[float]
) -> Projection:
  nearest_distance = math.inf
  nearest_progress = 0
  lat_scale = 111.32
  lon_scale = lat_scale * math.cos(point.lat * math.pi / 180)

  i = 0
  while i < len(route) - 1:
    from_point = route[i]
    to_point = route[i + 1]
    segment_km = cumulative[i + 1] - cumulative[i];

    if segment_km <= 0:
      i += 1
      continue

    dx = (to_point[1] - from_point[1]) * lon_scale
    dy = (to_point[0] - from_point[0]) * lat_scale
    px = (point.lon - from_point[1]) * lon_scale
    py = (point.lat - from_point[0]) * lat_scale

    denominator = dx * dx + dy * dy
    fraction = 0 if denominator <= 0 else min(1, max(0, (px * dx + py * dy) / denominator))

    projected: tuple[float, float] = (
      from_point[0] + (to_point[0] - from_point[0]) * fraction,
      from_point[1] + (to_point[1] - from_point[1]) * fraction
    )

    distance = haversine_km((point.lat, point.lon), projected)
    if distance < nearest_distance:
      nearest_distance = distance;
      nearest_progress = cumulative[i] + segment_km * fraction

    i += 1

  return Projection(
    progress_km=nearest_progress,
    distance_to_route_km=nearest_distance
  )

