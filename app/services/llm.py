import json
import warnings

from openai import AsyncOpenAI, ContentFilterFinishReasonError, LengthFinishReasonError
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel, ValidationError

from app.api.v1.routes.schemas import RouteIntent, StopLegEnum, StopSchema
from app.core.config import settings
from app.core.exceptions import UnclearRequestException

# Fail fast instead of the client defaults (600s timeout, 2 retries)
client = AsyncOpenAI(
  base_url=settings.LLM_API_ENDPOINT,
  api_key=settings.LLM_API_KEY,
  timeout=90.0,
  max_retries=1
)

# The local server adds its own top-level `metadata` ({"weight_versions": [...]}) where the SDK
# expects OpenAI's dict of strings, and `parse()` re-serializes the response, warning on every call
warnings.filterwarnings(
  "ignore",
  message=r"(?s)Pydantic serializer warnings:.*field_name='metadata'",
  category=UserWarning,
)

# Caps runaway generation, structured output can otherwise loop until the model limit
MAX_OUTPUT_TOKENS = 2048
REASONING_EFFORT: ReasoningEffort = "none"

# Chat completions instead of the responses API, the LiteLLM proxy turns responses
# requests into an empty `tools` array which vLLM rejects for some models (e.g. GLM)

intent_system_prompt = '''You are a motorcycle route planning assistant.
Extract a generic, structured route intent from the user's request. Do not plan road geometry or invent named places.

Route topology:
- start: the starting location.
- end: a named destination different from start. Keep it when the user also says "and back". Omit it entirely for loops (round trips from start with no destination).
- return_to_start: true when the trip returns to start. "Brno to Prague and back" means end="Prague" and true. A "50 km loop from Brno" has no end and true. "Brno to Prague" is false.

Target is {value, unit, mode}. Unit is "km" or "min". Mode is "around", "under", "at_least", or "open". Only include target when the user states a distance or duration; omit it otherwise.

Stops:
- stops includes exact places and generic discovery requests.
- request preserves the natural-language request for discovery stops. For exact places it is only the place name as it would be searched on a map, without words like "via" or "through": "via Mikulov" -> "Mikulov".
- count is the number of distinct places the rider wants for one discovery request, from 1 to 5. Interpret "a couple", "a pair", and "two" as 2; "a few" or "three" as 3; and other explicit quantities literally. Omit count when only one place is requested.
- resolution is "exact_place" for a named place ("via Mikulov") and "discover" for a category ("a nice cafe", "a castle").
- priority is "required" for must/visit/include/via and "preferred" for some/a nice/if possible/recommend.
- leg is "outbound", "return", or "whole_route". "On the way back" means "return". Use "whole_route" when either direction works, and always for stops on a loop.
- position is "any", "early", "middle", or "late". Generic coffee on the way back should be "middle". Use "any" when the rider did not indicate.
- include max_detour_km only when given or strongly implied.

Examples:
- "50 km loop from Brno" -> no end, target {50, km, around}, no stops.
- "50 km loop from Brno via Pernstejn" -> exact required stop, leg whole_route.
- "50 km loop from Brno with a nice castle" -> preferred discover stop, leg whole_route, position any.
- "loop from Brno past a couple of cool castles" -> one preferred discovery stop with count=2, leg whole_route.
- "Brno to Prague via Mikulov" -> end=Prague, exact required stop, leg outbound.
- "Brno to Prague and back, coffee on the way back" -> end=Prague, preferred discovery stop, leg return, position middle.

Curvature is "high" for explicitly curvy/twisty roads and "medium" for explicitly scenic/winding roads. Omit curvature when the rider did not request road curvature; use "low" only when they explicitly request low curvature. It is a Valhalla cost preference; never create synthetic curvature stops. Reflect explicit motorway and toll preferences. Keep notes concise.'''

async def parse_intent(instructions: str) -> RouteIntent:
  try:
    response = await client.chat.completions.parse(
      model=settings.LLM_MODEL,
      messages=[
        {"role": "system", "content": intent_system_prompt},
        {"role": "user", "content": instructions},
      ],
      response_format = RouteIntent,
      max_completion_tokens = MAX_OUTPUT_TOKENS,
      reasoning_effort = REASONING_EFFORT
    )
  # Output that breaks the schema or never finishes, providers behind a proxy
  # don't always enforce the schema constraints
  except (ValidationError, LengthFinishReasonError, ContentFilterFinishReasonError):
    raise UnclearRequestException() from None

  intent = response.choices[0].message.parsed
  if intent is None:
    raise UnclearRequestException()

  intent.start = intent.start.strip()
  if not intent.start:
    raise UnclearRequestException("Where should the route start? Add a starting place to the request")
  # Strict structured output makes every field required, so "no value" may come back as ""
  intent.end = (intent.end or "").strip() or None
  intent.stops = [stop for stop in intent.stops if stop.request.strip()]

  # Catch the model contradicting itself, both would otherwise pick the wrong planner
  if intent.end and intent.end.lower() == intent.start.lower():
    intent.end = None
    intent.return_to_start = True
  if any(stop.leg == StopLegEnum.Return for stop in intent.stops):
    intent.return_to_start = True

  return intent


class RouteSample(BaseModel):
  index: int
  progress_ratio: float
  lat: float
  lon: float
  location: str

class PoiSuggestion(BaseModel):
  stop_index: int
  name: str
  search_query: str
  sample_index: int

class PoiSuggestions(BaseModel):
  suggestions: list[PoiSuggestion]

poi_system_prompt = '''You are a motorcycle route planning assistant.
Suggest real, specifically named places for each requested stop along the supplied route.
- stops are indexed; set stop_index to the stop the suggestion belongs to.
- For each stop suggest at least count + 3 places, ordered best to worst, near different samples. Extra places are fallbacks in case some cannot be found. When count > 1 the rider will visit all of them, so prefer geographically distinct places.
- For small everyday places (cafe, restaurant, fuel) you usually don't know real names. Never invent a name; instead set search_query to the generic category word in the local language plus the town, e.g. "kavárna, Jihlava", and the search engine will find a real one there.
- samples are ordered reverse-geocoded points along the route. Respect each stop's position (early, middle, late, any) relative to progress_ratio.
- Every place must lie within max_distance_km of the route, so it must be close to one of the samples. Prefer a lesser-known place right next to the route over a famous one further away.
- Never invent coordinates: set sample_index to the sample the place is nearest to and give a precise search_query: the place's own name plus the village or town it is in.
- Only suggest places you are confident exist. Return an empty list if none are credible.'''

async def suggest_pois(
  instructions: str,
  stops: list[StopSchema],
  samples: list[RouteSample],
  max_distance_km: float
) -> list[PoiSuggestion]:
  payload = {
    "original_request": instructions,
    "max_distance_km": max_distance_km,
    "stops": [
      {
        "index": index,
        "request": stop.request,
        "count": stop.count or 1,
        "position": stop.position,
        "priority": stop.priority,
      }
      for index, stop in enumerate(stops)
    ],
    "samples": [sample.model_dump() for sample in samples],
  }

  response = await client.chat.completions.parse(
    model=settings.LLM_MODEL,
    messages=[
      {"role": "system", "content": poi_system_prompt},
      {"role": "user", "content": json.dumps(payload)},
    ],
    response_format = PoiSuggestions,
    max_completion_tokens = MAX_OUTPUT_TOKENS,
    reasoning_effort = REASONING_EFFORT
  )

  parsed = response.choices[0].message.parsed
  if parsed is None:
    return []
  return parsed.suggestions
