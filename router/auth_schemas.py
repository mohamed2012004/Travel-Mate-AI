from pydantic import BaseModel, EmailStr, Field


class AuthRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class AuthLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int | None = None
    email: str
    is_active: bool = True
