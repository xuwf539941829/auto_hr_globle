from __future__ import annotations

from datetime import datetime

from app.models.domain import FeedbackItem, FeedbackSummary
from app.schemas.feedback import CandidateFeedbackRequest
from app.services.candidate_service import candidate_service
from app.services.mock_data import store


class FeedbackService:
    def get_summary(self) -> FeedbackSummary:
        return store.build_feedback_summary()

    def add_feedback(self, candidate_id: str, payload: CandidateFeedbackRequest) -> FeedbackItem:
        detail = candidate_service.get_candidate_detail(candidate_id)
        item = FeedbackItem(
            id=f"fb-{len(store.feedback_items) + 1:03d}",
            candidate_id=candidate_id,
            candidate_name=detail.card.name,
            feedback_type=payload.feedback_type,  # type: ignore[arg-type]
            reason=payload.reason,
            detail=payload.detail,
            created_at=datetime.now(),
        )
        store.feedback_items.insert(0, item)
        return item


feedback_service = FeedbackService()
