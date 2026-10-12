from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException, EmptyReverseGeocodeResultException

class GeocodeGeometry(BaseModel):
  type: str
  coordinates: list[float]

class GeocodeProperty(BaseModel):
  full_address: str

class GeocodeFeature(BaseModel):
  id: str
  type: str
  geometry: GeocodeGeometry
  properties: GeocodeProperty

class GeocodeResult(BaseModel):
  type: str
  features: list[GeocodeFeature]

class Coordinates(BaseModel):
  lon: float
  lat: float

def geocode(place: str) -> Coordinates:
  url = settings.GEOCODE_URL + '/forward'
  response = httpx2.get(url, params={
    "q": place,
    "access_token": settings.GEOCODE_API_KEY
  })
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  if not result.features:
    raise EmptyGeocodeResultException(place)
  best_pick = result.features[0]

  return Coordinates(
    lon = best_pick.geometry.coordinates[0],
    lat = best_pick.geometry.coordinates[1]
  )

def reverse_geocode(point: Coordinates) -> str:
  url = settings.GEOCODE_URL + '/reverse'
  response = httpx2.get(url, params={
    "longitude": point.lon,
    "latitude": point.lat,
    "access_token": settings.GEOCODE_API_KEY,
  })
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  if not result.features:
    raise EmptyReverseGeocodeResultException(point.lat, point.lon)
  best_pick = result.features[0]

  return best_pick.properties.full_address



