from fastapi import APIRouter, Query

from app.services.candidate_service import candidate_service

router = APIRouter()


@router.get("")
def list_candidates(job_id: str = Query(default="job-001")):
    return candidate_service.list_candidates(job_id)


@router.get("/{candidate_id}")
def get_candidate(candidate_id: str, job_id: str = Query(default="job-001")):
    return candidate_service.get_candidate_detail(candidate_id, job_id)


@router.post("/{candidate_id}/collect")
def collect_candidate(candidate_id: str, job_id: str = Query(default="job-001")):
    return candidate_service.mark_action(candidate_id, "collect", job_id)


@router.post("/{candidate_id}/greet")
def greet_candidate(candidate_id: str, job_id: str = Query(default="job-001")):
    return candidate_service.mark_action(candidate_id, "greet", job_id)


@router.post("/{candidate_id}/reanalyze")
def reanalyze_candidate(candidate_id: str, job_id: str = Query(default="job-001")):
    return candidate_service.get_candidate_detail(candidate_id, job_id)
