from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.api.v1.users.routes import router as auth_router
from app.utils.migrations import run_migrations

setup_logging()

run_migrations()

logger = get_logger(__name__)

app = FastAPI(
  title=settings.PROJECT_NAME,
  debug=settings.DEBUG
)

app.include_router(auth_router)

@app.get("/health")
async def health_check():
  return {"status": "ok"}

@app.get("/")
async def root():
  """Root endpoint."""
  logger.debug("Root endpoint called")
  return {"message": "Welcome to exroute!"}
