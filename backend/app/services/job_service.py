from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException

from app.core.logging import get_logger
from app.models.domain import JobOption, JobProfile, JobProfileWorkbench, JobSummary
from app.schemas.jobs import CalibrateRequest, SampleResumeRequest
from app.services.boss_connector import BossConnectorError, boss_connector
from app.services.jd_translator import jd_translator
from app.services.mock_data import build_job_options, build_job_profile, store
from app.services.runtime_state_service import runtime_state_service
from app.services.sample_resume_analyzer import sample_resume_analyzer

logger = get_logger(__name__)


class JobService:
    def __init__(self) -> None:
        self._workbenches: dict[str, JobProfileWorkbench] = {}
        self._live_jobs_cache: list[JobOption] = []
        self._live_jobs_cached_at: datetime | None = None
        self._live_jobs_ttl = timedelta(seconds=45)
        persisted = runtime_state_service.load_workbench(store.job.id)
        if persisted is not None:
            self._workbenches[store.job.id] = persisted
            current = persisted.final_profile or persisted.sample_profile or persisted.jd_profile
            if current is not None:
                store.profile = current
                store.job.current_profile = current
                logger.info("Loaded persisted workbench for job %s", store.job.id)

    def list_jobs(self) -> list[JobOption]:
        if self._live_jobs_cache and self._live_jobs_cached_at and datetime.now() - self._live_jobs_cached_at < self._live_jobs_ttl:
            logger.info("Returning %s cached live jobs.", len(self._live_jobs_cache))
            return self._live_jobs_cache

        try:
            live_jobs = boss_connector.fetch_job_options()
            if live_jobs:
                self._live_jobs_cache = live_jobs
                self._live_jobs_cached_at = datetime.now()
                logger.info("Loaded %s live jobs from Boss.", len(live_jobs))
                return live_jobs
        except BossConnectorError as exc:
            logger.warning("Failed to load live jobs from Boss, return empty list: %s", exc)
        return []

    def get_current_job(self) -> JobSummary:
        return store.job

    def get_job(self, job_id: str) -> JobSummary:
        if job_id == store.job.id:
            return store.job

        options = {item.id: item for item in self.list_jobs()}
        option = options.get(job_id)
        if option is None:
            logger.warning("Requested unknown job_id: %s", job_id)
            raise HTTPException(status_code=404, detail="Job not found")

        profile = build_job_profile(
            job_id=job_id,
            version_id=f"{job_id}-profile-v1",
            version_name=option.profile_version_name,
        )
        profile.private_notes = [f"这是 {option.name} 的占位画像，建议尽快重新转译并校准。"]

        return JobSummary(
            id=option.id,
            name=option.name,
            city=option.city,
            status=option.status,
            raw_jd_text=f"{option.name} 的岗位描述占位内容。",
            current_profile=profile,
        )

    def get_current_profile(self, job_id: str) -> JobProfile:
        workbench = self.get_profile_workbench(job_id)
        return workbench.final_profile or workbench.sample_profile or workbench.jd_profile or self.get_job(job_id).current_profile

    def get_profile_workbench(self, job_id: str) -> JobProfileWorkbench:
        if job_id not in self._workbenches:
            persisted = runtime_state_service.load_workbench(job_id)
            if persisted is not None:
                self._workbenches[job_id] = persisted
                logger.info("Restored persisted workbench for job %s", job_id)
            else:
                job = self.get_job(job_id)
                self._workbenches[job_id] = JobProfileWorkbench(job_id=job_id, jd_profile=job.current_profile)
                logger.info("Initialized new workbench for job %s", job_id)
        return self._workbenches[job_id]

    def translate_jd(self, job_id: str, notes: str | None = None, raw_jd_text: str | None = None) -> JobProfile:
        job = self.get_job(job_id)
        source_jd = (raw_jd_text or job.raw_jd_text or "").strip()
        if not source_jd:
            source_jd = f"{job.name} 的岗位描述占位内容。"

        logger.info("Translating JD for job %s", job_id)
        profile = jd_translator.translate(
            job_id=job_id,
            job_name=job.name,
            raw_jd_text=source_jd,
            notes=notes,
        )

        workbench = self.get_profile_workbench(job_id)
        workbench.jd_profile = profile
        workbench.sample_profile = None
        workbench.final_profile = None
        self._persist_job_state(job_id, source_jd)
        logger.info("JD translated for job %s -> profile %s", job_id, profile.version_id)
        return profile

    def analyze_sample_resumes(self, job_id: str, payload: SampleResumeRequest) -> JobProfile:
        job = self.get_job(job_id)
        resumes = [resume.strip() for resume in payload.resumes if resume and resume.strip()]
        if not resumes:
            logger.warning("Sample resume analysis requested without resumes for job %s", job_id)
            raise HTTPException(status_code=400, detail="At least one sample resume is required")

        logger.info("Analyzing %s sample resumes for job %s", len(resumes), job_id)
        workbench = self.get_profile_workbench(job_id)
        base_profile = workbench.jd_profile or job.current_profile
        profile = sample_resume_analyzer.analyze(
            job_id=job_id,
            job_name=job.name,
            base_profile=base_profile,
            resumes=resumes,
            notes=payload.notes,
        )

        workbench.sample_profile = profile
        workbench.final_profile = None
        self._persist_job_state(job_id, job.raw_jd_text)
        logger.info("Sample-enhanced profile generated for job %s -> profile %s", job_id, profile.version_id)
        return profile

    def calibrate_profile(self, job_id: str, payload: CalibrateRequest) -> JobProfile:
        job = self.get_job(job_id)
        workbench = self.get_profile_workbench(job_id)

        if payload.base_stage == "jd":
            base_profile = workbench.jd_profile
        elif payload.base_stage == "sample":
            base_profile = workbench.sample_profile or workbench.jd_profile
        else:
            base_profile = workbench.sample_profile or workbench.jd_profile or job.current_profile

        if base_profile is None:
            logger.warning("Calibration requested without base profile for job %s", job_id)
            raise HTTPException(status_code=400, detail="No base profile available for calibration")

        profile = JobProfile(**base_profile.model_dump())
        profile.version_id = f"{job_id}-profile-v4-final"
        profile.version_name = "V4 最终执行画像"

        for competency in profile.competencies:
            if competency.key in payload.competency_weights:
                competency.weight = payload.competency_weights[competency.key]

        profile.competencies = sorted(profile.competencies, key=lambda item: (-item.weight, item.label))
        profile.industry_expansion.items = self._merge_unique_text(payload.industry_expansion, profile.industry_expansion.items)
        profile.exclude_rules.items = self._merge_unique_text(payload.exclude_rules, profile.exclude_rules.items)
        profile.private_notes = self._merge_unique_text(payload.manual_notes, profile.private_notes)
        profile.impact_summary = f"{job.name} 已综合 JD 初稿、优秀样本增强结果和 HR 校准意见，生成最终执行画像。"
        profile.translation_notes = [
            "这是最终执行画像。",
            f"校准基底：{'样本增强画像' if payload.base_stage == 'sample' and workbench.sample_profile else 'JD 初稿'}。",
            "它由 JD 转译、样本分析和 HR 微调共同生成。",
        ]

        workbench.final_profile = profile
        self._persist_job_state(job_id, job.raw_jd_text)
        logger.info("Final profile calibrated for job %s -> profile %s", job_id, profile.version_id)
        return profile

    def save_final_profile(self, job_id: str, profile: JobProfile) -> JobProfile:
        workbench = self.get_profile_workbench(job_id)
        if workbench.final_profile is None:
            raise HTTPException(status_code=400, detail="No final profile exists. Generate one first.")
        # Bump version_id on every manual edit so old candidates' screening_blueprint
        # version_id diverges from the new one, enabling the UI's old-version indicator.
        ts = datetime.now().strftime("%m%d%H%M")
        data = profile.model_dump()
        data["version_id"] = f"{workbench.final_profile.version_id}-e{ts}"
        data["version_name"] = workbench.final_profile.version_name
        data["job_id"] = job_id
        saved = JobProfile(**data)
        workbench.final_profile = saved
        raw_jd = store.job.raw_jd_text if job_id == store.job.id else ""
        self._persist_job_state(job_id, raw_jd)
        logger.info("Final profile manually edited for job %s", job_id)
        return saved

    @staticmethod
    def _merge_unique_text(primary: list[str], fallback: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in [*primary, *fallback]:
            cleaned = str(item).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    def _persist_job_state(self, job_id: str, raw_jd_text: str) -> None:
        workbench = self.get_profile_workbench(job_id)
        runtime_state_service.save_workbench(job_id, workbench)

        if job_id != store.job.id:
            return

        current = self.get_current_profile(job_id)
        store.profile = current
        store.job.current_profile = current
        store.job.raw_jd_text = raw_jd_text
        store.task.profile_version_id = current.version_id


job_service = JobService()
