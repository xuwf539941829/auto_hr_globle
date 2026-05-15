from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    name: str
    city: str
    raw_jd_text: str = Field(min_length=20)


class TranslateRequest(BaseModel):
    notes: str | None = None
    raw_jd_text: str | None = None


class CalibrateRequest(BaseModel):
    competency_weights: dict[str, int]
    manual_notes: list[str]
    industry_expansion: list[str]
    exclude_rules: list[str]
    base_stage: str | None = None


class SampleResumeRequest(BaseModel):
    resumes: list[str] = Field(min_length=1)
    notes: str | None = None


class ScreeningTaskCreateRequest(BaseModel):
    job_id: str
    profile_version_id: str


class ScreeningRunRequest(BaseModel):
    job_id: str
    pages: int = Field(default=1, ge=1, le=5)
    skip_seen: bool = True
