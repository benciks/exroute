from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException

class GeocodeFeature(BaseModel):
  lon: float
  lat: float
  # The place's own name, street address or town depending on what was found
  address_line1: str

class GeocodeResult(BaseModel):
  results: list[GeocodeFeature]

class Coordinates(BaseModel):
  lon: float
  lat: float

class Place(Coordinates):
  name: str

# One client for the whole app so connections to the geocoder are reused between calls
client = httpx2.AsyncClient()

async def geocode(
    place: str,
    lon: float | None = None,
    lat: float | None = None
  ) -> Place:
  params = {
    "text": place,
    "format": "json",
    "limit": "1",
    "apiKey": settings.GEOAPIFY_API_KEY
  }
  # Only ranks results, e.g. picks the Horní Poříčí near the start over its namesakes
  if lon is not None and lat is not None:
    params["bias"] = f"proximity:{lon},{lat}"

  # Search finds nothing for e.g. "Prague", autocomplete does
  for endpoint in ('/v1/geocode/search', '/v1/geocode/autocomplete'):
    response = await client.get(settings.GEOAPIFY_URL + endpoint, params=params)
    response.raise_for_status()

    result = GeocodeResult.model_validate(response.json())
    if result.results:
      best_pick = result.results[0]
      return Place(
        lon = best_pick.lon,
        lat = best_pick.lat,
        name = best_pick.address_line1
      )

  raise EmptyGeocodeResultException(place)
