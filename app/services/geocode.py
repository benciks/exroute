from pydantic import BaseModel
import httpx2

from app.core.config import settings

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
  url = settings.GEOCODE_URL + '/forward?q={place}&access_token={token}'.format(
    place=place, 
    token=settings.GEOCODE_API_KEY
  )
  response = httpx2.get(url)
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  best_pick = result.features[0]

  return Coordinates(
    lon = best_pick.geometry.coordinates[0],
    lat = best_pick.geometry.coordinates[1]
  )

def reverseGeocode(point: Coordinates) -> str:
  url = settings.GEOCODE_URL + '/reverse?longitude={logitude}&latitude={latitude}&access_token={token}'.format(
    logitude=point.lon, 
    latitude=point.lat,
    token=settings.GEOCODE_API_KEY
  )
  response = httpx2.get(url)
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  best_pick = result.features[0]

  return best_pick.properties.full_address



