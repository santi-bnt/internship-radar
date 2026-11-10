from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from app.services.safe_job_fetch import validate_job_url


class RawOpportunity(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    source_name: str = Field(min_length=1, max_length=100)
    source_url: str = Field(max_length=2000)
    external_id: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=180)
    location: str = Field(default="Unknown", max_length=240)
    description: str = Field(default="", max_length=100000)
    canonical_url: str = Field(default="", max_length=2000)
    posted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_url", "canonical_url")
    @classmethod
    def public_url(cls, value):
        return validate_job_url(value) if value else value


class DiscoverySearchQuery(BaseModel):
    mode: Literal["quick", "deep"] = "quick"
    query: str = Field(default="", max_length=600)
    areas: list[str] = Field(default_factory=list, max_length=15)
    countries: list[str] = Field(default_factory=list, max_length=6)
    opportunity_types: list[str] = Field(default_factory=lambda: ["Internship", "Research Internship", "Summer Research"], max_length=8)
    max_age_days: int | None = Field(default=None, ge=1, le=365)
    new_days: int = Field(default=3, ge=1, le=30)


class CompanyBoardInput(BaseModel):
    company: str = Field(min_length=1, max_length=180)
    ats: Literal["greenhouse", "lever", "ashby", "smartrecruiters", "workday"]
    board_id: str = Field(min_length=1, max_length=200)
    source_url: str = Field(max_length=2000)

    @field_validator("source_url")
    @classmethod
    def public_url(cls, value):
        return validate_job_url(value)
