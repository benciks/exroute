import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

class RouteCreate(BaseModel):
  instructions: str;

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

class CurvatureEnum(str, Enum):
  Low = 'low'
  Medium = 'medium'
  High = 'high'

class StopSchema(BaseModel):
  request: str
  count: int | None = Field(default=None, ge=1, le=5)
  resolution: StopResolutionEnum
  priority: StopPriorityEnum = StopPriorityEnum.Preferred
  leg: StopLegEnum = StopLegEnum.WholeRoute
  position: StopPositionEnum = StopPositionEnum.Any
  max_detour_km: float | None = Field(gt=0)

class RouteIntent(BaseModel):
  start: str
  end: str | None = None
  return_to_start: bool
  target: IntentTarget | None = None
  stops: list[StopSchema] = []
  curvature: CurvatureEnum | None = None
  avoid_motorways: bool = False
  avoid_tolls: bool = False
  notes: str = ""