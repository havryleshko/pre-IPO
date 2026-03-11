from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class JudgeFlag(BaseModel):
    flag_id: UUID
    section: str
    severity: Literal["amber", "red"]
    reason: str
    source_reference: str
    retry_attempted: bool
    retry_passed: bool
    improvement_suggestion: str | None = None


class JudgeOutput(BaseModel):
    validation_passed: bool
    flags: list[JudgeFlag] = Field(default_factory=list)
    export_locked: bool
    ifa_confirmed_flags: list[UUID] = Field(default_factory=list)
    validated_at: datetime
