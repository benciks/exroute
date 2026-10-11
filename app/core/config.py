from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  """"Application settings."""

  PROJECT_NAME: str = "exroute"
  DATABASE_URL: str
  DEBUG: bool = False

  JWT_SECRET: str
  JWT_ALGORITHM: str = "HS256"
  JWT_EXPIRATION: int = 30 # minutes

  LLM_API_ENDPOINT: str
  LLM_API_KEY: str
  LLM_MODEL: str = "command-a"

  GEOCODE_URL: str
  GEOCODE_API_KEY: str

  VALHALLA_URL: str

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8"
  )

settings = Settings()