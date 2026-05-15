from fastapi import APIRouter, File, Form, UploadFile

from app.models.domain import JobProfile
from app.schemas.jobs import CalibrateRequest, SampleResumeRequest, TranslateRequest
from app.services.job_service import job_service
from app.services.sample_resume_ingestion import sample_resume_ingestion_service

router = APIRouter()


@router.get("")
def list_jobs():
    return job_service.list_jobs()


@router.get("/current")
def get_current_job():
    return job_service.get_current_job()


@router.get("/{job_id}")
def get_job(job_id: str):
    return job_service.get_job(job_id)


@router.post("/{job_id}/translate")
def translate_job(job_id: str, payload: TranslateRequest):
    return job_service.translate_jd(job_id, payload.notes, payload.raw_jd_text)


@router.post("/{job_id}/samples/analyze")
def analyze_sample_resumes(job_id: str, payload: SampleResumeRequest):
    return job_service.analyze_sample_resumes(job_id, payload)


@router.get("/{job_id}/profiles/workbench")
def get_profile_workbench(job_id: str):
    return job_service.get_profile_workbench(job_id)


@router.post("/{job_id}/samples/analyze-upload")
async def analyze_uploaded_sample_resumes(
    job_id: str,
    notes: str | None = Form(default=None),
    pasted_resumes: list[str] = Form(default=[]),
    files: list[UploadFile] = File(default=[]),
):
    uploaded_items = await sample_resume_ingestion_service.save_and_extract(job_id, files)
    uploaded_resumes = [item["content"] for item in uploaded_items if item["content"]]
    payload = SampleResumeRequest(resumes=[*pasted_resumes, *uploaded_resumes], notes=notes)
    return job_service.analyze_sample_resumes(job_id, payload)


@router.get("/{job_id}/profiles/current")
def get_current_profile(job_id: str):
    return job_service.get_current_profile(job_id)


@router.post("/{job_id}/profiles/calibrate")
def calibrate_profile(job_id: str, payload: CalibrateRequest):
    return job_service.calibrate_profile(job_id, payload)


@router.put("/{job_id}/profiles/final")
def save_final_profile(job_id: str, profile: JobProfile):
    return job_service.save_final_profile(job_id, profile)
