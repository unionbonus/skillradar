from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class Envelope(BaseModel):
    code: int = 0
    data: Any = None
    message: str = "success"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str


class ScanIn(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    type: Literal["keyword", "topic", "author"] = "keyword"
    limit: int = Field(default=20, ge=1, le=50)
    watch: bool = False

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query required")
        return v


class KeywordIn(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    search_type: Literal["keyword", "topic", "author"] = "keyword"
    enabled: bool = True
    interval_hours: int = Field(default=6, ge=1, le=168)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query required")
        return v


class DecomposeIn(BaseModel):
    repo_url: str = Field(min_length=8, max_length=512)
    local_path: str | None = None

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://") or v.startswith("file://")):
            raise ValueError("repo_url must be http(s) or file://")
        return v


class SubscriptionConditions(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    specific_repos: list[str] = Field(default_factory=list)


class ChannelConfigIn(BaseModel):
    webhook_url: str | None = None
    secret: str | None = None
    email: str | None = None


class SubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    conditions: SubscriptionConditions = Field(default_factory=SubscriptionConditions)
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    channel: Literal["feishu", "wecom", "email"] = "feishu"
    channel_config: ChannelConfigIn = Field(default_factory=ChannelConfigIn)
    llm_config_id: UUID | None = None
    channel_config_id: UUID | None = None
    is_active: bool = True


class SubscriptionOut(BaseModel):
    subscription_id: UUID
    user_id: UUID
    name: str
    conditions: dict
    frequency: str
    channel: str
    has_webhook: bool
    llm_config_id: UUID | None = None
    channel_config_id: UUID | None = None
    is_active: bool
    last_sent_at: datetime | None
    created_at: datetime
