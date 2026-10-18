import json
import warnings

from openai import AsyncOpenAI, ContentFilterFinishReasonError, LengthFinishReasonError
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel, ValidationError

from app.api.v1.routes.schemas import RouteIntent, StopLegEnum, StopSchema
from app.core.config import settings
from app.core.exceptions import UnclearRequestException
from app.utils.poi import ProjectPoi

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
MAX_OUTPUT_TOKENS = 4096
REASONING_EFFORT: ReasoningEffort = "low"

# Chat completions instead of the responses API, the LiteLLM proxy turns responses
# requests into an empty `tools` array which vLLM rejects for some models (e.g. GLM)

intent_system_prompt = '''You are a motorcycle route planning assistant.
Extract a generic, structured route intent from the user's request. Do not plan road geometry or invent named places.

Route topology:
- start: the starting location.
- end: a named destination different from start. Keep it when the user also says "and back". Omit it entirely for loops (round trips from start with no destination).
- return_to_start: true when the trip returns to start. "Brno to Prague and back" means end="Prague" and true. A "50 km loop from Brno" has no end and true. "Brno to Prague" is false.

Target is {value, unit}. Unit is "km" or "min". Only include target when the user states a distance or duration; omit it otherwise.

Stops:
- stops includes exact places and generic discovery requests.
- request preserves the natural-language request for discovery stops. For exact places it is only the place name as it would be searched on a map, without words like "via" or "through": "via Mikulov" -> "Mikulov".
- count is the number of distinct places the rider wants for one discovery request, from 1 to 5. Interpret "a couple", "a pair", and "two" as 2; "a few" or "three" as 3; and other explicit quantities literally. Omit count when only one place is requested.
- resolution is "exact_place" for a named place ("via Mikulov") and "discover" for a category ("a nice cafe", "a castle").
- categories lists every allowed place category that satisfies a discover stop, e.g. coffee -> ["catering.cafe"], gas station -> ["service.vehicle.fuel"], lunch -> ["catering.restaurant"], castle -> ["tourism.sights.castle"], castle ruins -> ["tourism.sights.ruines"], lookout tower -> ["tourism.sights.tower"]. Leave it empty for exact places.
- priority is "required" for must/visit/include/via and "preferred" for some/a nice/if possible/recommend.
- leg is "outbound", "return", or "whole_route". "On the way back" means "return". Use "whole_route" when either direction works, and always for stops on a loop.
- position is "any", "early", "middle", or "late". Generic coffee on the way back should be "middle". Use "any" when the rider did not indicate.
- include max_detour_km only when given or strongly implied.

Examples:
- "50 km loop from Brno" -> no end, target {50, km}, no stops.
- "50 km loop from Brno via Pernstejn" -> exact required stop, leg whole_route.
- "50 km loop from Brno with a nice castle" -> preferred discover stop, categories ["tourism.sights.castle"], leg whole_route, position any.
- "loop from Brno past a couple of cool castles" -> one preferred discovery stop with count=2, categories ["tourism.sights.castle"], leg whole_route.
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
      reasoning_effort = REASONING_EFFORT,
      temperature=0.0
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


class PoiPick(BaseModel):
  stop_index: int
  candidate_ids: list[int]

class PoiPicks(BaseModel):
  picks: list[PoiPick]

poi_system_prompt = '''You are a motorcycle route planning assistant.
Pick the best places for each requested stop from that stop's candidates. Candidates are real places found along the route.
- stops are indexed; set stop_index to the stop the pick belongs to and candidate_ids to ids from that stop's own candidates.
- Order candidate_ids best to worst and give at least count + 3 when there are enough. Extra places are fallbacks in case some lie too close to each other. When count > 1 the rider will visit all of them, so prefer places with different progress_ratio.
- Candidates come from OpenStreetMap and can be mislabeled: skip ones whose name or categories show they are not what the rider asked for, e.g. an office, school or museum in a former castle building, or a name that is only a generic word.
- For sights prefer well-known, worthwhile places. For quick stops like coffee or fuel prefer places close to the route (low distance_to_route_km).
- progress_ratio is how far along the route the place lies, from 0 at the start to 1 at the end.
- Leave a stop out when none of its candidates fit.'''

async def pick_pois(
  instructions: str,
  stops: list[StopSchema],
  candidates: list[list[ProjectPoi]]
) -> list[PoiPick]:
  payload = {
    "original_request": instructions,
    "stops": [
      {
        "index": index,
        "request": stop.request,
        "count": stop.count or 1,
        "candidates": [
          {
            "id": id,
            "name": candidate.name,
            "categories": candidate.categories,
            "progress_ratio": round(candidate.progress_ratio, 2),
            "distance_to_route_km": round(candidate.distance_to_route_km, 1),
          }
          for id, candidate in enumerate(stop_candidates)
        ],
      }
      for index, (stop, stop_candidates) in enumerate(zip(stops, candidates))
    ],
  }

  response = await client.chat.completions.parse(
    model=settings.LLM_MODEL,
    messages=[
      {"role": "system", "content": poi_system_prompt},
      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ],
    response_format = PoiPicks,
    max_completion_tokens = MAX_OUTPUT_TOKENS,
    reasoning_effort = REASONING_EFFORT,
    temperature=0.4
  )

  parsed = response.choices[0].message.parsed
  if parsed is None:
    return []
  return parsed.picks
