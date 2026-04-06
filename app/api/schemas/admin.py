"""Pydantic schemas for admin authentication."""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user: dict  # {"username": str, "is_active": bool}
    csrf_token: str


class MeResponse(BaseModel):
    username: str
    is_active: bool


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str  # Min 8 chars, validated server-side
