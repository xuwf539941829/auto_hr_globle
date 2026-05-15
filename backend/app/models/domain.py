from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Grade = Literal["S", "A", "B", "C"]
TaskStatus = Literal["pending", "running", "paused", "completed", "failed"]


class MetricCard(BaseModel):
    label: str
    value: str
    delta: str | None = None


class DashboardSnapshot(BaseModel):
    active_job_name: str
    profile_version: str
    metrics: list[MetricCard]
    task_status: str
    task_progress: int
    latest_sync_at: str
    recent_feedback: list[str]
    top_candidates: list["CandidateCard"]


class CompetencyWeight(BaseModel):
    key: str
    label: str
    weight: int = Field(ge=0, le=100)
    note: str


class ProfileRule(BaseModel):
    title: str
    items: list[str]


class JobProfile(BaseModel):
    version_id: str
    version_name: str
    job_id: str
    hard_constraints: ProfileRule
    competencies: list[CompetencyWeight]
    industry_expansion: ProfileRule
    exclude_rules: ProfileRule
    private_notes: list[str]
    impact_summary: str
    translation_source: Literal["llm", "rules"] = "rules"
    translation_notes: list[str] = Field(default_factory=list)
    age_min: int | None = None
    age_max: int | None = None


class JobSummary(BaseModel):
    id: str
    name: str
    city: str
    status: str
    raw_jd_text: str
    current_profile: JobProfile


class JobProfileWorkbench(BaseModel):
    job_id: str
    jd_profile: JobProfile | None = None
    sample_profile: JobProfile | None = None
    final_profile: JobProfile | None = None


class JobOption(BaseModel):
    id: str
    name: str
    city: str
    salary_desc: str | None = None
    status: str
    profile_version_name: str


class LLMSettings(BaseModel):
    provider_label: str = "OpenAI Compatible"
    enabled: bool = False
    has_api_key: bool = False
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    api_style: Literal["chat_completions", "responses"] = "chat_completions"
    timeout_seconds: int = Field(default=45, ge=5, le=180)


class CandidateEvidence(BaseModel):
    type: Literal["action", "number", "timeline", "value", "risk"]
    title: str
    content: str
    impact: str
    confidence: float = Field(ge=0, le=1)


class CandidateConstraintCheck(BaseModel):
    item: str
    passed: bool
    reason: str


class CandidateDimensionCheck(BaseModel):
    key: str
    label: str
    weight: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    reason: str


class ResumeWorkEntry(BaseModel):
    company: str
    position: str
    start: str
    end: str
    summary: str


class ResumeEducationEntry(BaseModel):
    school: str
    degree: str
    start: str
    end: str
    summary: str


class ResumeDetailSection(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    work_experiences: list[ResumeWorkEntry]
    education_experiences: list[ResumeEducationEntry]
    action_terms: list[str]
    numeric_evidence: list[str]
    timeline_summary: list[str]
    risk_signals: list[str]


class ScreeningBlueprint(BaseModel):
    profile_version_id: str
    hard_filters: list[str]
    scoring_dimensions: list[CompetencyWeight]
    industry_targets: list[str]
    exclude_rules: list[str]
    private_notes: list[str]
    age_min: int | None = None
    age_max: int | None = None


class CandidateAnalysis(BaseModel):
    score: int = Field(ge=0, le=100)
    grade: Grade
    pass_flag: bool
    summary: str
    reasoning_summary: str
    llm_trace_id: str | None = None
    hard_constraint_check: list[CandidateConstraintCheck] = Field(default_factory=list)
    dimension_checks: list[CandidateDimensionCheck] = Field(default_factory=list)
    score_breakdown: list[MetricCard] = Field(default_factory=list)
    evidence_items: list[CandidateEvidence] = Field(default_factory=list)
    timeline_risks: list[str] = Field(default_factory=list)
    risk_items: list[str] = Field(default_factory=list)
    value_signals: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class CandidateCard(BaseModel):
    id: str
    name: str
    age: int
    education: str
    work_years: float
    current_company: str
    current_position: str
    grade: Grade
    score: int
    summary: str
    risk_tags: list[str]
    collected: bool
    greeted: bool
    collected_at: str | None = None
    greeted_at: str | None = None
    source: str = "mock"
    security_id: str | None = None
    lid: str | None = None
    encrypt_geek_id: str | None = None
    encrypt_job_id: str | None = None
    expect_id: str | None = None
    design_greeting: str | None = None


class CandidateDetail(BaseModel):
    card: CandidateCard
    timeline: list[str]
    original_resume: str
    parsed_resume: ParsedResume | None = None
    hr_resume_sections: list[ResumeDetailSection] = Field(default_factory=list)
    screening_blueprint: ScreeningBlueprint | None = None
    analysis: CandidateAnalysis


class ScreeningConfig(BaseModel):
    job_id: str
    profile_version_id: str
    max_pages: int = 10
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ScreeningTask(BaseModel):
    id: str
    job_id: str
    job_name: str = ""
    profile_version_id: str
    config: ScreeningConfig | None = None
    status: TaskStatus
    progress_current: int
    progress_total: int
    started_at: datetime
    updated_at: datetime
    message: str
    candidate_count: int = 0
    auto_pass_count: int = 0
    grade_counts: dict[str, int] = Field(default_factory=dict)


class FeedbackItem(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    feedback_type: Literal["positive", "negative", "manual_adjust"]
    reason: str
    detail: str
    created_at: datetime


class FeedbackSummary(BaseModel):
    job_id: str
    highlights: list[str]
    negative_clusters: list[str]
    positive_clusters: list[str]
    suggested_profile_shift: list[str]
    items: list[FeedbackItem]


DashboardSnapshot.model_rebuild()
