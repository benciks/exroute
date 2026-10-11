from fastapi import APIRouter, Depends 
from app.api.v1.users.models import User
from app.core.db import get_session
from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.api.v1.routes.schemas import RouteCreate
from app.api.v1.routes.service import RouteService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/routes", tags=["routes"])

@router.post("")
async def create_route(
  route_data: RouteCreate,
  # current_user: User = Depends(get_current_user),
  session: AsyncSession = Depends(get_session)
):
  logger.debug("Creating new route")
  try:
    result = await RouteService(session).create_route(route_data)
    return {
      "result": result
    }
  except Exception as e:
    logger.error(f"Failed to create route: {str(e)}")
    raise
