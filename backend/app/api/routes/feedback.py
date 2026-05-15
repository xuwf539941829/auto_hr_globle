from fastapi import APIRouter

from app.schemas.feedback import CandidateFeedbackRequest
from app.services.feedback_service import feedback_service

router = APIRouter()


@router.get("/summary")
def get_feedback_summary():
    return feedback_service.get_summary()


@router.post("/candidates/{candidate_id}")
def add_feedback(candidate_id: str, payload: CandidateFeedbackRequest):
    return feedback_service.add_feedback(candidate_id, payload)
