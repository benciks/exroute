import logging
import re
import sys

from app.core.config import settings

# The geocoder keys travel in the query string, so any logged URL would expose them:
# the HTTP client's request log and the messages of its errors
SECRET_PARAMS = re.compile(r"\b(api_key|access_token)=[^&\s'\"]+")

class RedactingFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    return SECRET_PARAMS.sub(r"\1=***", super().format(record))

def setup_logging() -> None:
  format_string = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(RedactingFormatter(format_string, datefmt="%H:%M:%S"))
  logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    handlers=[handler]
  )

def get_logger(name: str) -> logging.Logger:
  return logging.getLogger(name)
