from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.logging import get_logger
from app.api.v1.users.dependencies import get_current_user
from app.api.v1.users.models import User
from app.api.v1.users.schemas import LoginData, Token, UserCreate, UserResponse
from app.api.v1.users.service import UserService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

@router.post(
  "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
  user_data: UserCreate, session: AsyncSession = Depends(get_session)
) -> User:
  logger.debug(f"Registering user: {user_data.email}")
  return await UserService(session).create_user(user_data)

@router.post(
  "/login", response_model=Token
)
async def login(
  form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
  session: AsyncSession = Depends(get_session),
) -> Token:
  login_data = LoginData(email=form_data.username, password=form_data.password)
  logger.debug(f"Login attempt: {login_data.email}")
  return await UserService(session).authenticate(login_data)

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> User:
  return user