from pydantic import BaseModel, ConfigDict, EmailStr, Field
import uuid

class UserBase(BaseModel):
  email: EmailStr

class UserCreate(UserBase):
  password: str = Field(min_length=8, max_length=128)

class UserResponse(UserBase):
  model_config = ConfigDict(from_attributes=True)
  id: uuid.UUID

class Token(BaseModel):
  access_token: str
  token_type: str = "bearer"

class LoginData(BaseModel):
  email: EmailStr
  password: str
