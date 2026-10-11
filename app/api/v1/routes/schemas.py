from pydantic import BaseModel
from enum import Enum

class RouteCreate(BaseModel):
  instructions: str;

class TargetValueEnum(str, Enum):
  Km = 'km'
  Min = 'min'

class TargetModeEnum(str, Enum):
  Around = 'around'
  Under = 'under'
  At_least = 'at_least'
  Open = 'open'

class IntentTarget(BaseModel):
  value: int
  unit: TargetValueEnum
  mode: TargetModeEnum

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

class StopInfluenceEnum(str, Enum):
  OnRoute = 'on_route'
  RouteShaping = 'route_shaping'

class CurvatureEnum(str, Enum):
  Low = 'low'
  Medium = 'medium'
  High = 'high'

class StopSchema(BaseModel):
  request: str
  count: int
  resolution: StopResolutionEnum
  priority: StopPriorityEnum
  leg: StopLegEnum
  position: StopPositionEnum
  influence: StopInfluenceEnum
  order: int
  max_detour_km: int

class RouteIntent(BaseModel):
  start: str
  end: str
  return_to_start: bool
  target: IntentTarget
  stops: list[StopSchema]
  curvature: CurvatureEnum
  avoid_motorways: bool
  avoid_tolls: bool
  notes: str