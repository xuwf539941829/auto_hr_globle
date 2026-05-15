from fastapi import APIRouter, HTTPException

from app.schemas.settings import LLMSettingsUpdateRequest
from app.services.llm_trace_service import llm_trace_service
from app.services.settings_service import settings_service

router = APIRouter()


@router.get("/llm")
def get_llm_settings():
    return settings_service.get_llm_settings()


@router.post("/llm")
def update_llm_settings(payload: LLMSettingsUpdateRequest):
    return settings_service.update_llm_settings(payload)


@router.get("/llm/traces")
def list_llm_traces(limit: int = 30):
    return llm_trace_service.list_traces(limit=limit)


@router.get("/llm/traces/{trace_id}")
def get_llm_trace(trace_id: str):
    try:
        return llm_trace_service.get_trace(trace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Trace not found") from exc
