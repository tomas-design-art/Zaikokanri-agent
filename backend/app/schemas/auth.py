"""Auth schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class MeResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    department: str | None = None
    department_id: int | None = None


class LoginResponse(BaseModel):
    user: MeResponse
