import httpx2
import openai
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.api.v1.users.routes import router as auth_router
from app.api.v1.routes.routes import router as routes_router
from app.utils.migrations import run_migrations

setup_logging()

run_migrations()

logger = get_logger(__name__)

app = FastAPI(
  title=settings.PROJECT_NAME,
  debug=settings.DEBUG
)

app.add_middleware(
  CORSMiddleware,
  allow_origins=settings.CORS_ORIGINS,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(routes_router)

# The LLM, geocoders or Valhalla failing is not our bug, tell the client to retry
# instead of answering with a bare 500
@app.exception_handler(httpx2.HTTPError)
@app.exception_handler(openai.APIError)
async def upstream_error_handler(request: Request, exc: Exception) -> JSONResponse:
  logger.error(f"Upstream service failed on {request.url.path}: {exc!r}")
  return JSONResponse(
    status_code=status.HTTP_502_BAD_GATEWAY,
    content={"detail": "A routing service is unavailable right now, please try again"},
  )

@app.get("/health")
async def health_check():
  return {"status": "ok"}

@app.get("/")
async def root():
  """Root endpoint."""
  logger.debug("Root endpoint called")
  return {"message": "Welcome to exroute!"}
