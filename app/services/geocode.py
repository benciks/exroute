from collections.abc import Sequence

from pydantic import BaseModel
import httpx2

from app.core.config import settings
from app.core.exceptions import EmptyGeocodeResultException
from app.utils.geometry import haversine_km

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

class SearchArea(Coordinates):
  """A circle the place has to lie in, e.g. everywhere a trip can reasonably reach."""
  radius_km: float

# One client for the whole app so connections to the geocoder are reused between calls
client = httpx2.AsyncClient()

# Results compared per query, the first one is often a namesake, e.g. a shop called
# "Květiny Bouzov" next to the start instead of Bouzov castle
CANDIDATES = 5
# A stop this close to the start or end of the trip would not change the route
MIN_STOP_SPACING_KM = 2.0

def distance_km(a: Coordinates, b: Coordinates) -> float:
  return haversine_km((a.lat, a.lon), (b.lat, b.lon))

async def geocode(
    place: str,
    lon: float | None = None,
    lat: float | None = None,
    area: SearchArea | None = None,
    away_from: Sequence[Coordinates] = (),
  ) -> Place:
  """Coordinates of a named place.

  lon, lat only bias the ranking towards a point, e.g. the start of the trip. Results
  outside area or close to a place in away_from are skipped: a namesake 200 km off the trip
  (a model of Karlštejn castle in a miniature park) or next to its start (a florist called
  "Květiny Bouzov" in Olomouc) can't be the stop the rider meant. When none of the results
  fit, the search is repeated restricted to the area, which surfaces results ranked lower.
  """
  def fits(result: GeocodeFeature) -> bool:
    if area is not None and distance_km(area, result) > area.radius_km:
      return False
    return all(distance_km(other, result) >= MIN_STOP_SPACING_KM for other in away_from)

  params = {
    "text": place,
    "format": "json",
    "limit": str(CANDIDATES),
    "apiKey": settings.GEOAPIFY_API_KEY
  }
  # Only ranks results, e.g. picks the Horní Poříčí near the start over its namesakes
  if lon is not None and lat is not None:
    params["bias"] = f"proximity:{lon},{lat}"

  attempts = [params]
  if area is not None:
    attempts.append({**params, "filter": f"circle:{area.lon},{area.lat},{round(area.radius_km * 1000)}"})

  for attempt in attempts:
    # Search finds nothing for e.g. "Prague", autocomplete does
    for endpoint in ('/v1/geocode/search', '/v1/geocode/autocomplete'):
      response = await client.get(settings.GEOAPIFY_URL + endpoint, params=attempt)
      response.raise_for_status()

      result = GeocodeResult.model_validate(response.json())
      best_pick = next((r for r in result.results if fits(r)), None)
      if best_pick is not None:
        return Place(
          lon = best_pick.lon,
          lat = best_pick.lat,
          name = best_pick.address_line1
        )

  raise EmptyGeocodeResultException(place)
