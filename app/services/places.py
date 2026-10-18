import asyncio

from pydantic import BaseModel
import httpx2

from app.api.v1.routes.schemas import PoiCategoryEnum
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.poi import PoiCandidate

# Geoapify bills one credit per 20 returned places, so a segment costs exactly one credit
SEGMENT_LIMIT = 20

class PlaceProperty(BaseModel):
  place_id: str
  name: str | None = None
  lon: float
  lat: float
  categories: list[str] = []

class PlaceFeature(BaseModel):
  properties: PlaceProperty

class PlaceResult(BaseModel):
  features: list[PlaceFeature]

logger = get_logger(__name__)

# Requests take 0.4-8 s, slower segments are dropped
client = httpx2.AsyncClient(timeout=10.0)

async def search_segment(
  categories: list[PoiCategoryEnum],
  segment: list[tuple[float, float]],
  buffer_km: float
) -> list[PoiCandidate]:
  response = await client.post(
    settings.GEOAPIFY_URL + '/v2/places',
    params={"apiKey": settings.GEOAPIFY_API_KEY},
    json={
      "categories": [category.value for category in categories],
      "filter": {
        "type": "polyline",
        # GeoJSON is lon, lat while the route shape is lat, lon
        "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in segment]},
        "buffer": round(buffer_km * 1000),
      },
      "limit": SEGMENT_LIMIT,
    },
  )
  response.raise_for_status()

  result = PlaceResult.model_validate(response.json())
  return [
    PoiCandidate(
      id=feature.properties.place_id,
      lon=feature.properties.lon,
      lat=feature.properties.lat,
      name=feature.properties.name,
      categories=feature.properties.categories,
    )
    # A nameless place can't be shown to the rider
    for feature in result.features if feature.properties.name
  ]

# Searched segment by segment, one search over the whole route returns its first
# page from wherever the places are densest, e.g. 90 of 100 cafes from Brno alone
async def search_along_route(
  categories: list[PoiCategoryEnum],
  segments: list[list[tuple[float, float]]],
  buffer_km: float
) -> list[PoiCandidate]:
  if not categories:
    return []

  results = await asyncio.gather(
    *(search_segment(categories, segment, buffer_km) for segment in segments),
    return_exceptions=True
  )
  # Fail only when every segment did
  failed = [result for result in results if isinstance(result, BaseException)]
  if len(failed) == len(results):
    raise failed[0]
  if failed:
    logger.warning(f"{len(failed)} of {len(results)} POI segments failed: {failed[0]!r}")

  # Neighbouring segments overlap within the buffer, so a place can come back twice
  unique: dict[str, PoiCandidate] = {}
  for candidates in results:
    if isinstance(candidates, BaseException): continue
    for candidate in candidates:
      unique.setdefault(candidate.id, candidate)
  return list(unique.values())
