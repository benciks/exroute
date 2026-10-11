from pydantic import BaseModel, ConfigDict, EmailStr
import uuid

class UserBase(BaseModel):
  email: EmailStr

class UserCreate(UserBase):
  password: str

class UserResponse(UserBase):
  model_config = ConfigDict(from_attributes=True)
  id: uuid.UUID

class Token(BaseModel):
  access_token: str
  token_type: str = "bearer"

class LoginData(BaseModel):
  email: EmailStr
  password: str