"""
Database Schemas for Photographer Portfolio

Each Pydantic model maps to a MongoDB collection (lowercased class name).
- User -> "user"
- Album -> "album"
- Photo -> "photo"

Auth is email/password with hashed passwords. Roles: "admin" (photographer) and "user" (regular visitor after sign-up).
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="BCrypt hash of password")
    role: str = Field("user", description="user | admin")
    avatar_url: Optional[str] = Field(None, description="Profile picture URL")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Album(BaseModel):
    title: str = Field(..., description="Album title")
    description: Optional[str] = Field(None, description="Album description")
    cover_url: Optional[str] = Field(None, description="Cover image URL")
    owner_id: Optional[str] = Field(None, description="User id of owner (admin)")
    tags: List[str] = Field(default_factory=list, description="Tags for filtering")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Photo(BaseModel):
    album_id: str = Field(..., description="Album id")
    title: Optional[str] = Field(None, description="Photo title")
    description: Optional[str] = Field(None, description="Photo description")
    file_url: str = Field(..., description="Public URL to the photo file")
    file_name: Optional[str] = Field(None, description="Original filename")
    file_size: Optional[int] = Field(None, description="Size in bytes")
    width: Optional[int] = Field(None)
    height: Optional[int] = Field(None)
    downloadable: bool = Field(True, description="Whether visitors can download")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

