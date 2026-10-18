from fastapi import HTTPException, status

class NotFoundException(HTTPException):
  def __init__(self, detail: str = "Resource not found") -> None:
    super().__init__(status.HTTP_404_NOT_FOUND, detail)

class AlreadyExistsException(HTTPException):
  def __init__(self, detail: str = "Resource already exists") -> None:
    super().__init__(status.HTTP_409_CONFLICT, detail)

class UnauthorizedException(HTTPException):
  def __init__(self, detail: str = "Unauthorized") -> None:
    super().__init__(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})

class ForbiddenException(HTTPException):
  def __init__(self, detail: str = "Forbidden") -> None:
    super().__init__(status.HTTP_403_FORBIDDEN, detail)

class UnclearRequestException(HTTPException):
  def __init__(self, detail: str = "Could not understand the route request, try rephrasing it") -> None:
    super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)

class NoRouteFoundException(HTTPException):
  def __init__(self, detail: str = "No route found between points") -> None:
    super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)

class EmptyGeocodeResultException(HTTPException):
  def __init__(self, place: str) -> None:
    super().__init__(status.HTTP_404_NOT_FOUND, f"No coordinates found for '{place}'")
