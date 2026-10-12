from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  """Application settings."""

  PROJECT_NAME: str = "exroute"
  DATABASE_URL: str
  DEBUG: bool = False

  JWT_SECRET: str
  JWT_ALGORITHM: str = "HS256"
  JWT_EXPIRATION: int = 30 # minutes

  # Add back only when using the local models
  # LLM_API_ENDPOINT: str
  LLM_API_KEY: str
  LLM_MODEL: str = "gpt-6-astra"

  GEOCODE_URL: str
  GEOCODE_API_KEY: str
  MAPBOX_URL: str
  MAPBOX_API_KEY: str

  VALHALLA_URL: str

  # Browser apps allowed to call the API, the Vite dev server by default
  CORS_ORIGINS: list[str] = ["http://localhost:5173"]

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8"
  )

settings = Settings()