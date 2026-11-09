import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

class RouteCreate(BaseModel):
  # Bounded since the whole prompt goes to the LLM, a real request is a sentence or two
  instructions: str = Field(min_length=1, max_length=1000)

class RouteResponse(BaseModel):
  model_config = ConfigDict(from_attributes=True)
  id: uuid.UUID
  instructions: str
  distance_km: float
  duration_min: float
  polyline: str
  waypoints: list[dict]
  created_at: datetime

class TargetValueEnum(str, Enum):
  Km = 'km'
  Min = 'min'

class IntentTarget(BaseModel):
  value: int
  unit: TargetValueEnum

class StopResolutionEnum(str, Enum):
  ExactPlace = 'exact_place'
  Discover = 'discover'

class StopPriorityEnum(str, Enum):
  Required = 'required'
  Preferred = 'preferred'

class StopLegEnum(str, Enum):
  Outbound = 'outbound'
  Return = 'return'
  WholeRoute = 'whole_route'

class StopPositionEnum(str, Enum):
  Any = 'any'
  Early = 'early'
  Middle = 'middle'
  Late = 'late'

class CurvatureEnum(str, Enum):
  Low = 'low'
  Medium = 'medium'
  High = 'high'

class HeadingEnum(str, Enum):
  North = 'north'
  NorthEast = 'northeast'
  East = 'east'
  SouthEast = 'southeast'
  South = 'south'
  SouthWest = 'southwest'
  West = 'west'
  NorthWest = 'northwest'

# Geoapify place categories a discovery stop can search, kept to what riders stop for.
# Geoapify rejects the whole request on an unknown category, so the LLM can't make one up
class PoiCategoryEnum(str, Enum):
  Cafe = 'catering.cafe'
  Restaurant = 'catering.restaurant'
  FastFood = 'catering.fast_food'
  IceCream = 'catering.ice_cream'
  Pub = 'catering.pub'
  Bakery = 'commercial.food_and_drink.bakery'
  Fuel = 'service.vehicle.fuel'
  ChargingStation = 'service.vehicle.charging_station'
  Castle = 'tourism.sights.castle'
  Ruins = 'tourism.sights.ruines'
  Monastery = 'tourism.sights.monastery'
  Church = 'tourism.sights.place_of_worship'
  Tower = 'tourism.sights.tower'
  Memorial = 'tourism.sights.memorial'
  Bridge = 'tourism.sights.bridge'
  Viewpoint = 'tourism.attraction.viewpoint'
  Attraction = 'tourism.attraction'
  Museum = 'entertainment.museum'
  Peak = 'natural.mountain.peak'
  Water = 'natural.water'
  Beach = 'beach'
  Park = 'leisure.park'
  NationalPark = 'national_park'
  Hotel = 'accommodation.hotel'
  GuestHouse = 'accommodation.guest_house'
  CampSite = 'camping.camp_site'

class StopSchema(BaseModel):
  request: str
  count: int | None = Field(default=None, ge=1, le=5)
  resolution: StopResolutionEnum
  categories: list[PoiCategoryEnum] = []
  priority: StopPriorityEnum = StopPriorityEnum.Preferred
  leg: StopLegEnum = StopLegEnum.WholeRoute
  position: StopPositionEnum = StopPositionEnum.Any
  max_detour_km: float | None = Field(default=None, gt=0)

class RouteIntent(BaseModel):
  start: str
  end: str | None = None
  return_to_start: bool
  target: IntentTarget | None = None
  heading: HeadingEnum | None = None
  stops: list[StopSchema] = []
  curvature: CurvatureEnum | None = None
  avoid_motorways: bool = False
  avoid_tolls: bool = False
  notes: str = ""