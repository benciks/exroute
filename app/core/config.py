from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  """"Application settings."""

  PROJECT_NAME: str = "exroute"
  DATABASE_URL: str
  DEBUG: bool = False

  JWT_SECRET: str
  JWT_ALGORITHM: str = "HS256"
  JWT_EXPIRATION: int = 30 # minutes

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8"
  )

settings = Settings()