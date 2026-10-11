from typing import Annotated, Any, Mapping

from annotated_doc import Doc
from fastapi import HTTPException, status

class NotFoundException(HTTPException):
  def __init__(self, detail: str = "Resouce not found") -> None:
    super().__init__(status.HTTP_404_NOT_FOUND, detail)

class AlreadyExistsException(HTTPException):
  def __init__(self, detail = "Resource already exists") -> None:
    super().__init__(status.HTTP_409_CONFLICT, detail)

class UnauthorizedException(HTTPException):
  def __init__(self, detail: str = "Unauthorized") -> None:
    super().__init__(status.HTTP_401_UNAUTHORIZED, detail)

class ForbiddenException(HTTPException):
  def __init__(self, detail: str = "Forbidden") -> None:
    super().__init__(status.HTTP_403_FORBIDDEN, detail)