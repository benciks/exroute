from openai import OpenAI
from app.api.v1.routes.schemas import RouteIntent
from app.core.config import settings

client = OpenAI(
  api_key=settings.LLM_API_KEY,
  base_url=settings.LLM_API_ENDPOINT
)

intent_system_prompt = '''You are a motorcycle route planning assistant.
Extract a generic, structured route intent from the user's request. Do not plan road geometry or invent named places.

Route topology:
- start: the starting location.
- end: a named destination different from start. Keep it when the user also says "and back". Omit it entirely for loops (round trips from start with no destination).

Target is {value, unit, mode}. Unit is "km" or "min". Mode is "around", "under", "at_least", or "open". Only include target when the user states a distance or duration; omit it otherwise.

Stops:
- stops includes exact places and generic discovery requests.
- request preserves the natural-language request.
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

def parse_intent(instructions: str) -> RouteIntent | None:
    response = client.responses.parse(
      model=settings.LLM_MODEL,
      instructions=intent_system_prompt,
      input=instructions,
      text_format = RouteIntent
    )

    return response.output_parsed
