from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException, EmptyReverseGeocodeResultException

class GeocodeGeometry(BaseModel):
  type: str
  coordinates: list[float]

class GeocodeProperty(BaseModel):
  name: str
  # Mapbox only, the surrounding area e.g. "Kraj Vysočina, Česko"
  place_formatted: str | None = None

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

# One client for the whole app so connections to the geocoders are reused between calls
client = httpx2.AsyncClient()

async def geocode(
    place: str,
    lon: float | None = None,
    lat: float | None = None,
    layers: str | None = None,
    radius_km: float | None = None
  ) -> Place:
  url = settings.GEOCODE_URL + '/pelias/v1/search'
  params = {
    "text": place,
    "api_key": settings.GEOCODE_API_KEY
  }
  if lon is not None and lat is not None:
    params["focus.point.lon"] = str(lon)
    params["focus.point.lat"] = str(lat)
  # e.g. "venue" restricts results to POIs
  if layers:
    params["layers"] = layers
  # Unlike the focus point, which only ranks results, this excludes anything outside the circle
  if radius_km and lon is not None and lat is not None:
    params["boundary.circle.lon"] = str(lon)
    params["boundary.circle.lat"] = str(lat)
    params["boundary.circle.radius"] = str(radius_km)

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

# Mapbox instead of Pelias, as our Pelias has no town data and only returns
# addresses like "U Dálnice 620", while Mapbox returns the nearest town or village
async def reverse_geocode(point: Coordinates) -> str:
  url = settings.MAPBOX_URL + '/reverse'
  response = await client.get(url, params={
    "longitude": point.lon,
    "latitude": point.lat,
    "types": "place,locality",
    "limit": 1,
    "access_token": settings.MAPBOX_API_KEY,
  })
  response.raise_for_status()

  result = GeocodeResult.model_validate(response.json())
  if not result.features:
    raise EmptyReverseGeocodeResultException(point.lat, point.lon)
  best_pick = result.features[0]

  if best_pick.properties.place_formatted:
    return f"{best_pick.properties.name}, {best_pick.properties.place_formatted}"
  return best_pick.properties.name
