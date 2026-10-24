"""Auth schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import NewPassword


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: NewPassword


class MeResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    department: str | None = None
    department_id: int | None = None
    must_change_password: bool = False


class LoginResponse(BaseModel):
    user: MeResponse
