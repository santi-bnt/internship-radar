from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.normalization import validate_public_url

Status = Literal["Unknown", "Not Open Yet", "Open", "Recruiter Contacted", "Applying", "Applied", "Interview", "Accepted", "Rejected", "Closed"]
Priority = Literal["Very High", "High", "Medium", "Low"]
Eligibility = Literal["International students accepted", "Unknown", "Not eligible"]
YesNo = Literal["Yes", "No", "Unknown"]
Funding = Literal["Fully funded", "Paid", "Stipend", "Housing support", "Travel support", "Unfunded", "Unknown"]


class OpportunityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    program: str = Field(min_length=1, max_length=300)
    organization: str = Field(min_length=1, max_length=180)
    country: str = Field(default="Unknown", max_length=100)
    city: str = Field(default="Unknown", max_length=140)
    official_url: str = Field(min_length=1, max_length=2000)
    application_url: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=20000)
    research_areas: list[str] = Field(default_factory=list, max_length=30)
    lab: str = Field(default="", max_length=240)
    professor: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=12000)
    program_type: Literal["Unknown", "Research Internship", "Summer Research", "Industry Internship", "Visiting Research", "Fellowship", "Full Time"] = "Unknown"
    employment_type: str = Field(default="Unknown", max_length=80)
    compatibility_level: Literal["Unknown", "Partial", "Strong", "Low"] = "Unknown"
    compatibility_notes: str = Field(default="", max_length=6000)
    international_eligibility: Eligibility = "Unknown"
    eligibility_notes: str = Field(default="", max_length=12000)
    funding: list[Funding] = Field(default_factory=lambda: ["Unknown"], min_length=1, max_length=7)
    funding_notes: str = Field(default="", max_length=6000)
    recommendation_letters: Literal["Required", "Optional", "Not required", "Unknown"] = "Unknown"
    recommendation_notes: str = Field(default="", max_length=3000)
    status: Status = "Unknown"
    priority: Priority = "Medium"
    favorite: bool = False
    undergraduate_eligible: YesNo = "Unknown"
    citizenship_restriction: YesNo = "Unknown"
    host_required: YesNo = "Unknown"
    required_documents: list[str] = Field(default_factory=list, max_length=30)
    deadline: date | None = None
    deadline_at: datetime | None = None
    deadline_notes: str = Field(default="", max_length=4000)
    supporting_urls: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def consistent_deadline(self):
        if self.deadline_at and self.deadline and self.deadline_at.date() != self.deadline:
            raise ValueError("Deadline date must match the exact deadline's local date")
        if self.deadline_at and not self.deadline:
            self.deadline = self.deadline_at.date()
        if "Unknown" in self.funding and len(self.funding) > 1:
            raise ValueError("Use Unknown funding alone, or select confirmed funding types")
        return self

    @field_validator("official_url", "application_url")
    @classmethod
    def public_url(cls, value):
        return validate_public_url(value) if value else value

    @field_validator("supporting_urls")
    @classmethod
    def public_urls(cls, values):
        return list(dict.fromkeys(validate_public_url(value) for value in values))

    @field_validator("research_areas", "required_documents")
    @classmethod
    def short_items(cls, values):
        if any(len(value) > 240 for value in values):
            raise ValueError("Each item must be at most 240 characters")
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("deadline_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Exact deadlines require an explicit timezone")
        return value
