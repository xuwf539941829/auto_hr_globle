from pydantic import BaseModel


class CandidateFeedbackRequest(BaseModel):
    job_id: str
    feedback_type: str
    reason: str
    detail: str
