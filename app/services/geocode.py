from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException

class GeocodeGeometry(BaseModel):
  type: str
  coordinates: list[float]

class GeocodeProperty(BaseModel):
  name: str

class GeocodeFeature(BaseModel):
  type: str
  geometry: GeocodeGeometry
  properties: GeocodeProperty

class GeocodeResult(BaseModel):
  features: list[GeocodeFeature]

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
  url = settings.GEOCODE_URL + '/pelias/v1/search'
  params = {
    "text": place,
    "api_key": settings.GEOCODE_API_KEY
  }
  if lon is not None and lat is not None:
    params["focus.point.lon"] = str(lon)
    params["focus.point.lat"] = str(lat)

  response = await client.get(url, params=params)
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  if not result.features:
    raise EmptyGeocodeResultException(place)
  best_pick = result.features[0]

  return Place(
    lon = best_pick.geometry.coordinates[0],
    lat = best_pick.geometry.coordinates[1],
    name = best_pick.properties.name
  )
