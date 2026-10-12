import uuid

from fastapi import APIRouter, Depends, Response
from app.api.v1.users.models import User
from app.core.db import get_session
from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.api.v1.routes.schemas import RouteCreate, RouteResponse
from app.api.v1.routes.service import RouteService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/routes", tags=["routes"])

@router.post("")
async def create_route(
  route_data: RouteCreate,
  current_user: User = Depends(get_current_user),
  session: AsyncSession = Depends(get_session)
):
  logger.debug("Creating new route")
  try:
    result = await RouteService(session).create_route(current_user.id, route_data)
    return {
      "result": result
    }
  except Exception as e:
    logger.error(f"Failed to create route: {str(e)}")
    raise

@router.get("", response_model=list[RouteResponse])
async def list_routes(
  current_user: User = Depends(get_current_user),
  session: AsyncSession = Depends(get_session)
):
  return await RouteService(session).list_routes(current_user.id)

@router.get("/{route_id}/gpx")
async def export_gpx(
  route_id: uuid.UUID,
  current_user: User = Depends(get_current_user),
  session: AsyncSession = Depends(get_session)
):
  gpx = await RouteService(session).get_gpx(route_id, current_user.id)
  return Response(
    content=gpx,
    media_type="application/gpx+xml",
    headers={"Content-Disposition": f'attachment; filename="route-{route_id}.gpx"'}
  )
