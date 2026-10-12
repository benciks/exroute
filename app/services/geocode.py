from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException, EmptyReverseGeocodeResultException

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

def geocode(
    place: str,
    lon: float | None = None,
    lat: float | None = None
  ) -> Coordinates:
  url = settings.GEOCODE_URL + '/pelias/v1/search'
  params = {
    "text": place,
    "api_key": settings.GEOCODE_API_KEY
  }
  if lon and lat:
    params["focus.point.lon"] = str(lon)
    params["focus.point.lat"] = str(lat)

  response = httpx2.get(url, params=params)
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
  url = settings.GEOCODE_URL + '/pelias/v1/reverse'
  response = httpx2.get(url, params={
    "point.lon": point.lon,
    "point.lat": point.lat,
    "api_key": settings.GEOCODE_API_KEY,
  })
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  if not result.features:
    raise EmptyReverseGeocodeResultException(point.lat, point.lon)
  best_pick = result.features[0]

  return best_pick.properties.name



