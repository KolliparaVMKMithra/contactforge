from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0


class HunterKeyStat(BaseModel):
    index: int
    key_suffix: str
    status: str = "standby"
    requests_made: int = 0
    credits_available: Optional[int] = None
    credits_used: Optional[int] = None
    reset_date: Optional[str] = None
    error: Optional[str] = None


class KeyStateInput(BaseModel):
    index: int = Field(..., ge=0)
    credits_available: Optional[int] = None
    credits_used: Optional[int] = None
    reset_date: Optional[str] = None
    status: Optional[str] = None


class SearchRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    max_results: int = Field(default=100, ge=1, le=500)
    hunter_api_keys: list[str] = Field(default_factory=list)
    active_key_index: int = Field(default=0, ge=0)
    key_states: list[KeyStateInput] = Field(default_factory=list)


class CheckKeysRequest(BaseModel):
    hunter_api_keys: list[str] = Field(..., min_length=1)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


class SearchResponse(BaseModel):
    company_name: str
    domain: Optional[str] = None
    website: Optional[str] = None
    contacts: list[Contact]
    pages_scanned: int = 0
    sources_used: list[str] = []
    message: str = ""
    enrichment_errors: list[str] = []
    hunter_key_stats: list[HunterKeyStat] = []
    active_key_index: int = 0
