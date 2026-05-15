from __future__ import annotations

import json
from uuid import uuid4

from app.core.logging import get_logger
from app.services.llm_trace_service import llm_trace_service

logger = get_logger("app.llm")

MAX_LOG_CHARS = 8000


def new_trace_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def sanitize_payload(payload: dict) -> dict:
    cleaned = json.loads(json.dumps(payload))
    if "api_key" in cleaned:
        cleaned["api_key"] = "***"
    if "Authorization" in cleaned:
        cleaned["Authorization"] = "Bearer ***"
    return cleaned


def truncate_text(text: str) -> str:
    if len(text) <= MAX_LOG_CHARS:
        return text
    return f"{text[:MAX_LOG_CHARS]}\n...[truncated {len(text) - MAX_LOG_CHARS} chars]"


def log_llm_request(trace_id: str, endpoint: str, payload: dict) -> None:
    llm_trace_service.record_request(trace_id, endpoint, sanitize_payload(payload))
    logger.info(
        "LLM_REQUEST trace_id=%s endpoint=%s payload=%s",
        trace_id,
        endpoint,
        truncate_text(json.dumps(sanitize_payload(payload), ensure_ascii=False, indent=2)),
    )


def log_llm_response(trace_id: str, raw_response: str) -> None:
    llm_trace_service.record_response(trace_id, raw_response)
    logger.info(
        "LLM_RESPONSE trace_id=%s body=%s",
        trace_id,
        truncate_text(raw_response),
    )


def log_llm_error(trace_id: str, message: str) -> None:
    llm_trace_service.record_error(trace_id, message)
    logger.warning("LLM_ERROR trace_id=%s detail=%s", trace_id, message)
